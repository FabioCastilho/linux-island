"""Página "IA" da ilha expandida: o Clawd mostra o que cada agente (sessão do Claude Code) faz.

À esquerda, uma dock com um botão por sessão (rosto do Clawd + ponto de estado); à direita, o
detalhe da escolhida: mascote animado, tarefa, subagentes e atalhos para a pasta e o terminal.
"""
import time

from gi.repository import Gdk, Gio, GLib, Gtk

from claude_sessions import ago, read_sessions, read_subagents
from clawd_sprite import SpriteView
from i18n import _
from sessions_view import BLUE, ORANGE, Dot
from terminal_focus import focus_session
from views import clip, label

MAX_AGENTS = 5
SLEEP_AFTER_S = 30 * 60   # aguardando você há tanto tempo: o Clawd cochila
CHEER_FOR_S = 8           # acabou de terminar: comemora por alguns segundos
STATUS = {  # estado do Claude Code -> (texto, cor)
    "busy": ("Trabalhando…", BLUE),
    "idle": ("Aguardando você", ORANGE),
}


def mood(session, now=None):
    """Animação do Clawd para a sessão: busy, done, idle, sleep ou alert."""
    now = time.time() if now is None else now
    status = session["status"]
    if status == "busy":
        return "busy"
    if status == "idle":
        age = now - session["since"]
        return "done" if age < CHEER_FOR_S else ("sleep" if age > SLEEP_AFTER_S else "idle")
    return "idle" if status == "?" else "alert"


def status_text(session):
    text, color = STATUS.get(session["status"], ("Precisa de você", ORANGE))
    return _(text), color


class RailButton(Gtk.Button):
    """Um agente na dock: o rosto do Clawd com um ponto de estado no canto."""

    def __init__(self, on_pick):
        super().__init__()
        self.sid = None
        self.set_can_focus(False)
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.get_style_context().add_class("ia-rail")
        self.sprite = SpriteView(46)
        self.dot = Dot()
        self.dot.set_halign(Gtk.Align.END)
        self.dot.set_valign(Gtk.Align.START)
        self.dot.set_margin_top(3)
        self.dot.set_margin_end(3)
        overlay = Gtk.Overlay()
        overlay.add(self.sprite)
        overlay.add_overlay(self.dot)
        self.add(overlay)
        self.connect("clicked", lambda _b: on_pick(self.sid))

    def set(self, session, selected):
        self.sid = session["sid"]
        self.sprite.set_anim(mood(session))
        self.dot.color = status_text(session)[1]
        self.dot.queue_draw()
        ctx = self.get_style_context()
        (ctx.add_class if selected else ctx.remove_class)("selected")
        self.set_tooltip_text(session["project"])


class IAPage(Gtk.Box):
    WIDTH = 420

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)
        self.sessions, self.selected = [], None
        self.cwd, self.pid = "", None

        head = Gtk.Box(spacing=8)
        title = label("title")
        title.set_text(_("IA · Claude Code"))
        self.summary = label("dim small", 1.0)
        head.pack_start(title, False, False, 0)
        head.pack_end(self.summary, True, True, 0)
        self.pack_start(head, False, False, 0)

        # --- com sessões: dock + detalhe
        self.body = Gtk.Box(spacing=10)
        self.rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.rail.set_valign(Gtk.Align.START)
        self.buttons = [RailButton(self.pick) for _i in range(MAX_AGENTS)]
        for b in self.buttons:
            self.rail.pack_start(b, False, False, 0)
        self.body.pack_start(self.rail, False, False, 0)
        self.body.pack_start(self._build_detail(), True, True, 0)
        self.pack_start(self.body, False, False, 0)

        # --- sem sessões: o Clawd dorme
        self.empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.empty_sprite = SpriteView(130, "sleep")
        self.empty_sprite.set_halign(Gtk.Align.CENTER)
        empty_label = label("dim", 0.5)
        empty_label.set_text(_("Nenhuma sessão ativa"))
        self.empty.pack_start(self.empty_sprite, False, False, 0)
        self.empty.pack_start(empty_label, False, False, 0)
        self.empty.set_margin_top(8)
        self.empty.set_margin_bottom(8)
        self.pack_start(self.empty, False, False, 0)

        self._timer = None
        self.connect("map", self._start)
        self.connect("unmap", self._stop)

    def _build_detail(self):
        detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        detail.get_style_context().add_class("ia-detail")
        pic = Gtk.Box()
        pic.get_style_context().add_class("ia-pic")
        self.sprite = SpriteView(120)
        self.sprite.set_halign(Gtk.Align.CENTER)
        self.sprite.set_hexpand(True)
        pic.add(self.sprite)
        detail.pack_start(pic, False, False, 0)

        top = Gtk.Box(spacing=8)
        top.set_margin_top(4)
        self.name = label("title", 0.0, True)
        self.age = label("dim small", 1.0)
        top.pack_start(self.name, True, True, 0)
        top.pack_end(self.age, False, False, 0)
        detail.pack_start(top, False, False, 0)
        self.state = label("small", 0.0)
        self.task = label("dim small", 0.0, True)
        detail.pack_start(self.state, False, False, 0)
        detail.pack_start(self.task, False, False, 0)

        self.sub_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.sub_box.set_margin_top(4)
        self.sub_box.set_size_request(-1, 3 * 20)  # altura fixa: a ilha não pula ao trocar de agente
        self.sub_rows = []
        for _i in range(3):
            row = Gtk.Box(spacing=6)
            dot = Dot()
            text = label("small", 0.0, True)
            row.pack_start(dot, False, False, 0)
            row.pack_start(text, True, True, 0)
            self.sub_rows.append((row, dot, text))
            self.sub_box.pack_start(row, False, False, 0)
        self.no_subs = label("dim small", 0.0)
        self.no_subs.set_text(_("Sem subagentes ativos"))
        self.sub_box.pack_start(self.no_subs, False, False, 0)
        detail.pack_start(self.sub_box, False, False, 0)

        btns = Gtk.Box(spacing=6)
        btns.set_margin_top(6)
        for text, cb in ((_("Abrir pasta"), self._open), (_("Ir ao terminal"), self._terminal)):
            b = Gtk.Button(label=text)
            b.set_can_focus(False)
            b.get_style_context().add_class("chip")
            b.connect("clicked", lambda _b, f=cb: f())
            btns.pack_start(b, False, False, 0)
        detail.pack_start(btns, False, False, 0)
        return detail

    # --- ações -----------------------------------------------------------------
    def _open(self):
        if self.cwd:
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(self.cwd, None), None)

    def _terminal(self):
        """Foca a janela do terminal; sem terminal à vista (ex.: tmux), abre a pasta."""
        if not (self.pid and focus_session(self.pid)):
            self._open()

    def pick(self, sid):
        if sid and sid != self.selected:
            self.selected = sid
            self._render()

    # --- atualização -----------------------------------------------------------
    def _start(self, *_a):
        self.refresh()
        if self._timer is None:
            self._timer = GLib.timeout_add_seconds(2, self.refresh)

    def _stop(self, *_a):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def refresh(self):
        self.sessions = read_sessions()[:MAX_AGENTS]
        sids = [s["sid"] for s in self.sessions]
        if self.selected not in sids:
            self.selected = sids[0] if sids else None
        self._render()
        return True

    def _render(self):
        sessions = self.sessions
        busy = sum(1 for s in sessions if s["status"] == "busy")
        waiting = sum(1 for s in sessions if s["status"] != "busy")
        self.summary.set_text(
            _("{b} trabalhando · {w} esperam você").format(b=busy, w=waiting) if sessions else "")
        self.body.set_visible(bool(sessions))
        self.empty.set_visible(not sessions)
        for i, button in enumerate(self.buttons):
            if i < len(sessions):
                button.set(sessions[i], sessions[i]["sid"] == self.selected)
                button.show_all()
            else:
                button.hide()
        current = next((s for s in sessions if s["sid"] == self.selected), None)
        if current:
            self._show_detail(current)

    def _show_detail(self, s):
        self.cwd, self.pid = s["cwd"], s["pid"]
        self.sprite.set_anim(mood(s))
        self.name.set_text(s["project"])
        self.age.set_text(ago(s["since"]))
        text, color = status_text(s)
        self.state.set_text(text)
        r, g, b = color
        self.state.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(r, g, b, 1))
        shown = s["prompt"] or s["title"] or s["name"] or ""
        self.task.set_text(_("Você: {t}").format(t=clip(shown.replace("\n", " "), 60))
                           if s["prompt"] else clip(shown, 60))
        subs = read_subagents(s["sid"], limit=len(self.sub_rows))
        for i, (row, dot, text_label) in enumerate(self.sub_rows):
            if i < len(subs):
                a = subs[i]
                dot.color = BLUE if a["running"] else (0.45, 0.45, 0.5)
                dot.queue_draw()
                text_label.set_text(clip(f"{a['type']} · {a['desc']}" if a["desc"] else a["type"], 46))
                row.show_all()
            else:
                row.hide()
        self.no_subs.set_visible(not subs)
