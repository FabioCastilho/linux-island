"""Agenda: eventos normalizados, alerta de reunião (lógica pura) e o controlador.

Lógica pura recebe `now` (datetime com fuso) para ser testável com relógio fixo.
O controlador busca a cada 5 min e recalcula o alerta a cada 30 s pelo relógio
de parede (funciona depois de suspender o PC).
"""
import math
import threading
import urllib.error
import re
from datetime import date, datetime, time as dtime, timedelta

from gi.repository import GLib

from google_calendar import AuthError, GoogleCalendar, MissingAppError
from i18n import _, weekday

POLL_S = 5 * 60
TICK_S = 30
GRACE = timedelta(minutes=5)  # o alerta continua um pouco depois do início
SKIP_TYPES = {"workingLocation"}


# --- lógica pura -----------------------------------------------------------------
def _local(dt):
    return dt.astimezone()


def _parse_when(when, tz_now):
    """(datetime com fuso, dia inteiro?) de um start/end da API."""
    if "dateTime" in when:
        return _local(datetime.fromisoformat(when["dateTime"])), False
    d = datetime.fromisoformat(when["date"])
    return d.replace(tzinfo=tz_now.tzinfo), True


def _meet_link(item):
    link = item.get("hangoutLink")
    if not link:
        for ep in (item.get("conferenceData") or {}).get("entryPoints") or []:
            if ep.get("entryPointType") == "video":
                link = ep.get("uri")
                break
    return link if isinstance(link, str) and link.startswith("https://") else None


def normalize(items, now):
    """Itens crus da API -> eventos ordenados, sem cancelados/recusados/local de trabalho."""
    events = []
    for it in items:
        if it.get("status") == "cancelled" or it.get("eventType") in SKIP_TYPES:
            continue
        if any(a.get("self") and a.get("responseStatus") == "declined"
               for a in it.get("attendees") or []):
            continue
        try:
            start, all_day = _parse_when(it.get("start") or {}, now)
            end, _allday = _parse_when(it.get("end") or it.get("start") or {}, now)
        except (KeyError, ValueError, TypeError):
            continue
        link = it.get("htmlLink")
        events.append({
            "id": it.get("id", ""), "title": (it.get("summary") or _("(sem título)")).strip(),
            "start": start, "end": end, "all_day": all_day, "meet": _meet_link(it),
            "html": link if isinstance(link, str) and link.startswith("https://") else None,
        })
    events.sort(key=lambda e: (e["start"], not e["all_day"]))
    return events


def alert_event(now, events, lead_min):
    """Reunião que deve aparecer na pílula agora: start - lead <= now < start + GRACE."""
    lead = timedelta(minutes=lead_min)
    for ev in events:
        if ev["all_day"]:
            continue
        if ev["start"] - lead <= now < min(ev["start"] + GRACE, ev["end"]):
            return ev
    return None


def alert_key(ev):
    """Identifica o alerta: se o evento for remarcado, alerta de novo."""
    return (ev["id"], ev["start"].isoformat())


def countdown(now, ev):
    if ev["all_day"]:
        return _("dia todo")
    if now >= ev["start"]:
        return _("agora") if now < ev["end"] else _("terminou")
    mins = math.ceil((ev["start"] - now).total_seconds() / 60)
    if mins < 60:
        return _("em {n} min").format(n=mins)
    h, m = divmod(mins, 60)
    return (_("em {h} h {m:02d}").format(h=h, m=m) if m
            else _("em {h} h").format(h=h))


def day_label(day, today):
    if day == today:
        return _("Hoje")
    if day == today + timedelta(days=1):
        return _("Amanhã")
    return f"{weekday(day.weekday(), True)} {day.day:02d}/{day.month:02d}"


def upcoming(now, events, days):
    """[(rótulo do dia, [eventos ainda não terminados])] dos próximos `days` dias."""
    today = now.date()
    last = today + timedelta(days=days - 1)
    groups = {}
    for ev in events:
        if ev["end"] <= now:
            continue
        day = max(ev["start"].date(), today) if ev["all_day"] else ev["start"].date()
        if day > last:
            continue
        groups.setdefault(day, []).append(ev)
    return [(day_label(d, today), groups[d]) for d in sorted(groups)]


# --- criação de evento (lógica pura) -------------------------------------------
MAX_TITLE = 200
MIN_DURATION, MAX_DURATION = 5, 24 * 60


def parse_date(text, today):
    """'hoje', 'amanhã', 'dd/mm', 'dd/mm/aaaa' ou 'aaaa-mm-dd' -> date. ValueError se inválida."""
    t = (text or "").strip().lower()
    if t in ("", "hoje", "today", "hoy"):
        return today
    if t in ("amanhã", "amanha", "tomorrow", "mañana", "manana"):
        return today + timedelta(days=1)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", t)
        if not m:
            raise ValueError("data")
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
    return date(y, mo, d)  # ValueError se o dia/mês não existir


def parse_time(text):
    """'14:30', '14h30', '14h' ou '14' -> time. ValueError se inválida."""
    m = re.fullmatch(r"(\d{1,2})(?:[:h](\d{2})?)?", (text or "").strip().lower())
    if not m:
        raise ValueError("hora")
    return dtime(int(m.group(1)), int(m.group(2) or 0))  # ValueError fora de 0-23/0-59


def build_event(title, day, start=None, duration_min=60):
    """Corpo para a API do Google. `start` None = dia inteiro. ValueError se inválido.

    Só leva o essencial (título e horário): sem convidados, local ou lembretes."""
    title = (title or "").strip()
    if not title:
        raise ValueError("título")
    if len(title) > MAX_TITLE:
        raise ValueError("título longo")
    if start is None:
        return {"summary": title, "start": {"date": day.isoformat()},
                "end": {"date": (day + timedelta(days=1)).isoformat()}}
    if not MIN_DURATION <= int(duration_min) <= MAX_DURATION:
        raise ValueError("duração")
    begin = datetime.combine(day, start).astimezone()  # horário local, com o fuso do sistema
    end = begin + timedelta(minutes=int(duration_min))
    return {"summary": title, "start": {"dateTime": begin.isoformat()},
            "end": {"dateTime": end.isoformat()}}


# --- controlador (lado GTK) ---------------------------------------------------------
class Agenda:
    """on_change() quando a lista/estado muda; on_alert(evento|None); on_status(texto, ok)."""

    def __init__(self, cfg, on_change, on_alert, on_status, play_sound):
        self.cfg = cfg
        self.on_change = on_change
        self.on_alert = on_alert
        self.on_status = on_status
        self.play_sound = play_sound
        self.google = GoogleCalendar()
        self.events = []
        self.alert = None
        self._dismissed = set()
        self._sounded = set()
        self._busy = False
        self._poll_id = None
        self.status = ((_("Conectado"), True) if self.google.connected
                       else (_("Não conectado"), False))
        GLib.timeout_add_seconds(TICK_S, lambda: self.tick() or True)
        if self.google.connected:
            self._start_polling()

    @property
    def connected(self):
        return self.google.connected

    @property
    def can_create(self):
        """Criar eventos exige a chave ligada E a permissão realmente concedida pelo Google."""
        return self.google.connected and self.cfg["agenda_write"] and self.google.can_write

    def _set_status(self, text, ok):
        self.status = (text, ok)
        self.on_status(text, ok)

    # conexão
    def login(self):
        self._set_status(_("Aguardando login no navegador…"), False)

        def work():
            try:
                self.google.login(write=self.cfg["agenda_write"])
                GLib.idle_add(self._logged_in)
            except (AuthError, urllib.error.URLError, OSError, ValueError, KeyError) as e:
                msg = _("Falha no login: {erro}").format(erro=e)  # `e` some ao sair do except
                GLib.idle_add(lambda: self._set_status(msg, False) and False)

        threading.Thread(target=work, daemon=True).start()

    def _logged_in(self):
        self._set_status(_("Conectado"), True)
        self._start_polling()
        return False

    def disconnect(self):
        self.google.disconnect()
        self._stop_polling()
        self.events = []
        self._set_status(_("Desconectado"), False)
        self.on_change()
        self.tick()

    def apply_write_setting(self):
        """Chamado quando a chave "Permitir criar eventos" muda."""
        if self.cfg["agenda_write"]:
            if self.google.connected and not self.google.can_write:
                self.login()  # pede a permissão nova (o Google mostra a tela de consentimento)
        elif self.google.can_write:
            self.disconnect()  # revoga o token com escrita; reconectar volta a ser só leitura

    def create_event(self, body, done):
        """Cria o evento fora da thread da UI. done(ok, mensagem) roda na thread da UI."""
        if not self.can_create:
            done(False, _("Criação de eventos desligada ou sem permissão"))
            return

        def work():
            ok, msg = True, ""
            try:
                self.google.create_event(body)
            except AuthError as e:
                ok, msg = False, str(e)
            except (urllib.error.URLError, OSError, ValueError) as e:
                ok, msg = False, _("Falha ao criar o evento: {erro}").format(erro=e)
            if ok:
                GLib.idle_add(self.refresh)
            GLib.idle_add(lambda: done(ok, msg) and False)

        threading.Thread(target=work, daemon=True).start()

    # busca
    def _start_polling(self):
        if self._poll_id is None:
            self._poll_id = GLib.timeout_add_seconds(POLL_S, lambda: self.refresh() or True)
        self.refresh()

    def _stop_polling(self):
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = None

    def refresh(self):
        if self._busy or not self.google.connected or not self.cfg["agenda_enabled"]:
            return
        self._busy = True
        now = datetime.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=self.cfg["agenda_days"])

        def work():
            items, err = None, None
            try:
                items = self.google.fetch_events(start, end)
            except MissingAppError as e:
                err = ("noapp", str(e))
            except AuthError as e:
                err = ("auth", str(e))
            except (urllib.error.URLError, OSError, ValueError) as e:
                err = ("net", str(e))
            GLib.idle_add(self._done, items, err)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, items, err):
        self._busy = False
        if err and err[0] in ("auth", "noapp"):
            self._stop_polling()
            self.events = []
            if err[0] == "noapp":  # token guardado, mas o app não está configurado
                self._set_status(_("Credenciais do app do Google não configuradas"), False)
            else:
                self._set_status(_("Reconecte sua conta do Google"), False)
        elif err:
            print(f"[island] agenda indisponível: {err[1]}")  # mantém o que já tinha
        else:
            self.events = normalize(items, datetime.now().astimezone())
            if not self.status[1]:
                self._set_status(_("Conectado"), True)
        self.on_change()
        self.tick()
        return False

    # alerta
    def tick(self):
        now = datetime.now().astimezone()
        ev = None
        if self.cfg["agenda_enabled"] and self.cfg["agenda_alert"]:
            ev = alert_event(now, self.events, self.cfg["agenda_lead_min"])
            if ev and alert_key(ev) in self._dismissed:
                ev = None
        changed = (ev is None) != (self.alert is None) or (
            ev and self.alert and alert_key(ev) != alert_key(self.alert))
        self.alert = ev
        if ev and self.cfg["agenda_sound"] and alert_key(ev) not in self._sounded:
            self._sounded.add(alert_key(ev))
            self.play_sound(self.cfg["agenda_sound_name"], self.cfg["agenda_sound_volume"])
        if changed:
            self.on_alert(ev)

    def dismiss(self):
        if self.alert:
            self._dismissed.add(alert_key(self.alert))
            self.tick()
