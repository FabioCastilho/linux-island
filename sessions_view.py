"""Página "Sessões" da ilha expandida: as sessões do Claude Code abertas agora."""
import math

from gi.repository import Gdk, Gio, GLib, Gtk

from claude_sessions import ago, read_sessions
from i18n import _
from icons import glyph_button
from terminal_focus import focus_session
from views import clip, label

ORANGE = (0.98, 0.62, 0.20)   # esperando você
BLUE = (0.36, 0.66, 1.0)      # trabalhando
MAX_ROWS = 5
STATUS = {  # estado do Claude Code -> (texto, cor)
    "busy": ("Trabalhando…", BLUE),
    "idle": ("Aguardando você", ORANGE),
}


class Dot(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.color = ORANGE
        self.set_size_request(10, 10)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", lambda _w, cr: (
            cr.set_source_rgb(*self.color), cr.arc(5, 5, 4.5, 0, 2 * math.pi), cr.fill()))


class SessionRow(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.get_style_context().add_class("session-row")
        self.cwd, self.pid = "", None
        top = Gtk.Box(spacing=8)
        self.dot = Dot()
        self.name = label("title", 0.0, True)
        self.badge = label("badge")
        self.badge.set_text("Claude")
        self.age = label("dim small", 1.0)
        self.open_btn = Gtk.Button()
        self.open_btn.set_image(Gtk.Image.new_from_icon_name("folder-open-symbolic",
                                                              Gtk.IconSize.BUTTON))
        self.open_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.open_btn.set_can_focus(False)
        self.open_btn.get_style_context().add_class("control")
        self.open_btn.set_tooltip_text(_("Abrir a pasta do projeto"))
        self.open_btn.connect("clicked", lambda *_a: self._open())
        self.term_btn, _g = glyph_button("terminal", 15, self._focus_terminal,
                                         _("Ir para o terminal desta sessão"))
        top.pack_start(self.dot, False, False, 0)
        top.pack_start(self.name, True, True, 0)
        top.pack_start(self.badge, False, False, 0)
        top.pack_start(self.age, False, False, 0)
        top.pack_start(self.term_btn, False, False, 0)
        top.pack_start(self.open_btn, False, False, 0)
        self.prompt = label("dim small", 0.0, True)
        self.prompt.set_margin_start(18)
        self.state = label("small", 0.0)
        self.state.set_margin_start(18)
        for w in (top, self.prompt, self.state):
            self.pack_start(w, False, False, 0)

    def _focus_terminal(self):
        """Foca a janela do terminal; sem terminal à vista (ex.: tmux), abre a pasta."""
        if not (self.pid and focus_session(self.pid)):
            self._open()

    def _open(self):
        if self.cwd:
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(self.cwd, None), None)

    def set(self, s):
        self.cwd, self.pid = s["cwd"], s["pid"]
        text, color = STATUS.get(s["status"], (s["status"], (0.6, 0.6, 0.6)))
        self.dot.color = color
        self.dot.queue_draw()
        self.name.set_text(s["project"])
        self.age.set_text(ago(s["since"]))
        shown = s["prompt"] or s["title"] or s["name"]
        self.prompt.set_text(_("Você: {t}").format(t=clip(shown.replace("\n", " "), 60))
                             if s["prompt"] else clip(shown, 60))
        self.state.set_text(_(text))
        r, g, b = color
        self.state.override_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(r, g, b, 1))


class SessionsPage(Gtk.Box):
    WIDTH = 420

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)
        head = Gtk.Box(spacing=8)
        title = label("title")
        title.set_text(_("Sessões do Claude Code"))
        self.count = label("dim small", 1.0)
        head.pack_start(title, False, False, 0)
        head.pack_end(self.count, True, True, 0)
        self.pack_start(head, False, False, 0)

        self.rows = [SessionRow() for _i in range(MAX_ROWS)]
        for r in self.rows:
            self.pack_start(r, False, False, 0)
        self.empty = label("dim", 0.5)
        self.empty.set_text(_("Nenhuma sessão ativa"))
        self.empty.set_margin_top(14)
        self.empty.set_margin_bottom(14)
        self.pack_start(self.empty, False, False, 0)
        self._timer = None
        self.connect("map", self._start)
        self.connect("unmap", self._stop)

    def _start(self, *_a):
        self.refresh()
        if self._timer is None:
            self._timer = GLib.timeout_add_seconds(2, self.refresh)

    def _stop(self, *_a):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def refresh(self):
        sessions = read_sessions()
        self.count.set_text(_("{n} sessões").format(n=len(sessions)) if len(sessions) != 1
                            else _("1 sessão"))
        for i, row in enumerate(self.rows):
            if i < len(sessions):
                row.set(sessions[i])
                row.show_all()
            else:
                row.hide()
        self.empty.set_visible(not sessions)
        return True
