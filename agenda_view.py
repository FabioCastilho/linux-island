"""Página "Agenda" da ilha expandida e o aviso de reunião na pílula."""
from datetime import date, datetime

from gi.repository import Gio, Gtk

from agenda import countdown, events_by_day, month_weeks, shift_month
from i18n import _, long_date, month, weekday
from icons import GLYPHS, Glyph, glyph_button
from views import clip, icon, label

MAX_ROWS = 5
CAL_ICON = "calendar"  # glifos próprios (icons.py): o tema do sistema pode não ter estes
VIDEO_ICON = "video"


def open_url(url):
    if url and url.startswith("https://"):
        Gio.AppInfo.launch_default_for_uri(url, None)


def pill_button(text, icon_name, cb, cls="water-main"):
    btn = Gtk.Button()
    box = Gtk.Box(spacing=6)
    if icon_name:
        box.pack_start(Glyph(icon_name, 14) if icon_name in GLYPHS else icon(icon_name, 14),
                       False, False, 0)
    lb = Gtk.Label(label=text)
    box.pack_start(lb, False, False, 0)
    btn.add(box)
    btn.set_can_focus(False)
    btn.get_style_context().add_class(cls)
    btn.connect("clicked", lambda *_a: cb())
    return btn


class MeetingPill(Gtk.Box):
    """Miolo da pílula quando uma reunião está chegando."""

    def __init__(self):
        super().__init__(spacing=8)
        self.pack_start(Glyph(CAL_ICON, 14), False, False, 0)
        self.title = label("clock")
        self.when = label("dim")
        self.video = Glyph(VIDEO_ICON, 14)
        for w in (self.title, self.when, self.video):
            self.pack_start(w, False, False, 0)

    def update(self, ev, now):
        self.title.set_text(clip(ev["title"], 28))
        self.when.set_text(countdown(now, ev))
        self.video.set_visible(bool(ev["meet"]))


class AgendaPage(Gtk.Box):
    WIDTH = 420

    def __init__(self, agenda, open_settings):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.agenda = agenda
        self.open_settings = open_settings
        self.month = date.today().replace(day=1)  # mês mostrado
        self.sel = date.today()                    # dia selecionado
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        head.pack_start(Glyph(CAL_ICON, 16), False, False, 0)
        self.title = label("title")
        head.pack_start(self.title, False, False, 0)
        nxt, _g = glyph_button("right", 14, lambda: self._go(1), _("Próximo mês"))
        prv, _g = glyph_button("left", 14, lambda: self._go(-1), _("Mês anterior"))
        head.pack_end(nxt, False, False, 0)
        head.pack_end(prv, False, False, 0)
        today = pill_button(_("Hoje"), None, self._today, "water-snooze")
        head.pack_end(today, False, False, 4)
        self.pack_start(head, False, False, 0)

        self.grid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.pack_start(self.grid_box, False, False, 0)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.pack_start(self.body, False, False, 0)

        foot = Gtk.Box(spacing=8)
        self.status = label("dim small")
        foot.pack_start(self.status, True, True, 0)
        self.new_btn = pill_button(_("Novo evento"), "plus", self._new_event, "water-snooze")
        self.new_btn.show_all()  # antes do no_show_all, senão o conteúdo do botão fica escondido
        self.new_btn.set_no_show_all(True)  # só aparece com a criação de eventos liberada
        foot.pack_end(self.new_btn, False, False, 0)
        self.pack_start(foot, False, False, 0)

    def _new_event(self):
        from event_dialog import EventDialog
        if self.agenda.can_create:
            EventDialog(self.agenda)

    def _go(self, step):
        self.month = shift_month(self.month, step)
        self.update(self.agenda.cfg)

    def _today(self):
        self.month, self.sel = date.today().replace(day=1), date.today()
        self.update(self.agenda.cfg)

    def _pick(self, day):
        self.sel = day
        self.month = day.replace(day=1)
        self.update(self.agenda.cfg)

    # --- conteúdo ---------------------------------------------------------
    def update(self, cfg):
        self.new_btn.set_visible(self.agenda.can_create)
        for box in (self.grid_box, self.body):
            for c in box.get_children():
                box.remove(c)
        now = datetime.now().astimezone()
        a = self.agenda
        self.title.set_text(f"{month(self.month.month)} {self.month.year}")
        self._build_grid(events_by_day(a.events) if a.connected else {}, now.date())
        if not a.connected:
            self.status.set_text("")
            self._empty(_("Entre com sua conta do Google para ver seus eventos."),
                        pill_button(_("Configurar"), "preferences-system-symbolic",
                                    self.open_settings, "water-snooze"))
        else:
            self.status.set_text(_("atualizado {hora}").format(hora=f"{datetime.now():%H:%M}")
                                 if a.status[1] else _("sem conexão"))
            if a.alert:
                self.body.pack_start(self._next_card(a.alert, now), False, False, 4)
            evs = events_by_day(a.events).get(self.sel, [])
            d = label("dim small")
            d.set_text(long_date(self.sel).upper())
            d.set_margin_top(4)
            self.body.pack_start(d, False, False, 0)
            if not evs:
                self._empty(_("Sem eventos neste dia."), None)
            for ev in evs[:MAX_ROWS]:
                self.body.pack_start(self._row(ev, now), False, False, 0)
            if len(evs) > MAX_ROWS:
                more = label("dim small")
                more.set_text(_("+{n} eventos").format(n=len(evs) - MAX_ROWS))
                self.body.pack_start(more, False, False, 0)
        self.grid_box.show_all()
        self.body.show_all()

    def _build_grid(self, by_day, today):
        head = Gtk.Box(homogeneous=True)
        for i in (6, 0, 1, 2, 3, 4, 5):  # domingo primeiro
            lb = label("dim small", 0.5)
            lb.set_text(weekday(i, True)[:3])
            head.pack_start(lb, True, True, 0)
        self.grid_box.pack_start(head, False, False, 0)
        for week in month_weeks(self.month):
            row = Gtk.Box(homogeneous=True, spacing=2)
            for day in week:
                row.pack_start(self._day_button(day, by_day.get(day), today), True, True, 0)
            self.grid_box.pack_start(row, False, False, 0)

    def _day_button(self, day, evs, today):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_can_focus(False)
        ctx = btn.get_style_context()
        ctx.add_class("cal-day")
        for cond, cls in ((day.month != self.month.month, "other"), (day == today, "today"),
                          (day == self.sel, "selected")):
            if cond:
                ctx.add_class(cls)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        num = label("small", 0.5)
        num.set_text(str(day.day))
        dot = label("cal-dot", 0.5)
        dot.set_text("●" if evs else " ")
        box.pack_start(num, False, False, 0)
        box.pack_start(dot, False, False, 0)
        btn.add(box)
        if evs:
            btn.set_tooltip_text("\n".join(
                (e["title"] if e["all_day"] else f"{e['start']:%H:%M} {e['title']}")
                for e in evs[:6]))
        btn.connect("clicked", lambda *_a, d=day: self._pick(d))
        return btn

    def _empty(self, text, button):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(6)
        lb = label("dim", 0.5)
        lb.set_text(text)
        box.pack_start(lb, False, False, 0)
        if button:
            button.set_halign(Gtk.Align.CENTER)
            box.pack_start(button, False, False, 0)
        self.body.pack_start(box, False, False, 0)

    def _next_card(self, ev, now):
        card = Gtk.Box(spacing=12)
        card.get_style_context().add_class("day")
        for side in ("start", "end"):
            getattr(card, f"set_margin_{side}")(0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_margin_start(12)
        t = label("title")
        t.set_text(clip(ev["title"], 30))
        w = label("dim small")
        w.set_text(f"{ev['start']:%H:%M}–{ev['end']:%H:%M} · {countdown(now, ev)}")
        texts.pack_start(t, False, False, 0)
        texts.pack_start(w, False, False, 0)
        card.pack_start(texts, True, True, 0)
        actions = Gtk.Box(spacing=6)
        actions.set_margin_end(10)
        actions.set_valign(Gtk.Align.CENTER)
        if ev["meet"]:
            actions.pack_start(pill_button(_("Entrar"), VIDEO_ICON, lambda: (
                open_url(ev["meet"]), self.agenda.dismiss())), False, False, 0)
        actions.pack_start(pill_button(_("Dispensar"), None, self.agenda.dismiss, "water-snooze"),
                           False, False, 0)
        card.pack_start(actions, False, False, 0)
        return card

    def _row(self, ev, now):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_can_focus(False)
        btn.get_style_context().add_class("agenda-row")
        row = Gtk.Box(spacing=10)
        when = label("time")
        when.set_width_chars(6)
        when.set_text(_("dia todo") if ev["all_day"] else f"{ev['start']:%H:%M}")
        title = label("small")
        title.set_text(clip(ev["title"], 34))
        row.pack_start(when, False, False, 0)
        row.pack_start(title, True, True, 0)
        if not ev["all_day"] and ev["start"].date() == now.date() and now < ev["end"]:
            c = label("dim small", 1.0)
            c.set_text(countdown(now, ev))
            row.pack_start(c, False, False, 0)
        if ev["meet"]:
            row.pack_start(Glyph(VIDEO_ICON, 13), False, False, 0)
        btn.add(row)
        btn.connect("clicked", lambda *_a: open_url(ev["meet"] or ev["html"]))
        return btn
