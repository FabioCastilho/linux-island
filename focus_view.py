"""Página "Foco" da ilha expandida: pomodoro e timer."""
import math

from gi.repository import Gtk

import palette
from focus import PHASES, TIMER_STEP_MIN, fmt
from i18n import _
from icons import Glyph, glyph_button
from views import label
from widgets import Tweened

COLORS = {"short": (0.30, 0.78, 0.52), "long": (0.36, 0.66, 1.0), "timer": (0.65, 0.55, 0.98)}


def phase_color(phase):
    """O foco usa a cor do tema; as pausas e o timer têm as suas."""
    return palette.FOCUS if phase == "focus" else COLORS[phase]
LABELS = {"focus": "Foco", "short": "Pausa", "long": "Pausa longa", "timer": "Timer"}


class FocusRing(Tweened, Gtk.DrawingArea):
    def __init__(self, size=132, width=9):
        super().__init__()
        self._tween_init()
        self.fraction = 1.0
        self._to = 1.0
        self.size, self.width = size, width
        self.color = palette.FOCUS
        self.fg = (1, 1, 1)
        self.set_size_request(size, size)
        self.set_halign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        c = self.size / 2
        r = c - self.width / 2 - 1
        cr.set_line_width(self.width)
        cr.set_source_rgba(*self.fg, 0.12)
        cr.arc(c, c, r, 0, 2 * math.pi)
        cr.stroke()
        if self.fraction > 0.004:
            cr.set_line_cap(1)
            cr.set_source_rgb(*self.color)
            cr.arc(c, c, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * self.fraction)
            cr.stroke()


class RoundDots(Gtk.DrawingArea):
    """Uma bolinha por foco do ciclo; as feitas ficam cheias."""

    def __init__(self):
        super().__init__()
        self.total, self.done = 4, 0
        self.color = palette.FOCUS
        self.fg = (1, 1, 1)
        self.set_size_request(self.total * 14, 10)
        self.set_halign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def set_state(self, done, total):
        if (done, total) != (self.done, self.total):
            self.done, self.total = done, total
            self.set_size_request(total * 14, 10)
            self.queue_draw()

    def _draw(self, _w, cr):
        for i in range(self.total):
            x = 5 + i * 14
            if i < self.done:
                cr.set_source_rgb(*self.color)
                cr.arc(x, 5, 4, 0, 2 * math.pi)
                cr.fill()
            else:
                cr.set_source_rgba(*self.fg, 0.25)
                cr.set_line_width(1.4)
                cr.arc(x, 5, 3.6, 0, 2 * math.pi)
                cr.stroke()


class FocusPage(Gtk.Box):
    WIDTH = 420

    def __init__(self, focus):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.focus = focus
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        head.pack_start(Glyph("timer", 16), False, False, 0)
        title = label("title")
        title.set_text(_("Foco"))
        head.pack_start(title, False, False, 0)
        self.pack_start(head, False, False, 0)

        chips = Gtk.Box(spacing=6, homogeneous=True)
        self.chips = {}
        for phase in PHASES:
            b = Gtk.Button(label=_(LABELS[phase]))
            b.set_can_focus(False)
            b.get_style_context().add_class("chip")
            b.connect("clicked", lambda _b, p=phase: self.focus.set_phase(p))
            chips.pack_start(b, True, True, 0)
            self.chips[phase] = b
        self.pack_start(chips, False, False, 0)

        overlay = Gtk.Overlay()
        self.ring = FocusRing()
        overlay.add(self.ring)
        self.clock = label("timer-clock", 0.5)
        self.clock.set_halign(Gtk.Align.CENTER)
        self.clock.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.clock)
        self.pack_start(overlay, False, False, 0)

        ctrls = Gtk.Box(spacing=18)
        ctrls.set_halign(Gtk.Align.CENTER)
        reset, _g = glyph_button("reset", 17, self.focus.reset, _("Reiniciar a fase"))
        self.play_btn, self.play_glyph = glyph_button("play", 22, self.focus.toggle,
                                                      _("Iniciar ou pausar"))
        self.play_btn.get_style_context().add_class("main")
        skip, _g2 = glyph_button("skip", 17, self.focus.skip, _("Pular para a próxima fase"))
        for b in (reset, self.play_btn, skip):
            ctrls.pack_start(b, False, False, 0)
        self.pack_start(ctrls, False, False, 0)

        adj = Gtk.Box(spacing=8)
        adj.set_halign(Gtk.Align.CENTER)
        for text, step in (("−5", -TIMER_STEP_MIN), ("+5", TIMER_STEP_MIN)):
            b = Gtk.Button(label=text + " min")
            b.set_can_focus(False)
            b.get_style_context().add_class("chip")
            b.connect("clicked", lambda _b, s=step: self.focus.adjust_timer(s))
            adj.pack_start(b, False, False, 0)
        self.adjust = adj
        adj.set_no_show_all(True)
        self.pack_start(adj, False, False, 0)

        self.dots = RoundDots()
        self.count = label("dim small", 0.5)
        self.pack_start(self.dots, False, False, 0)
        self.pack_start(self.count, False, False, 0)
        self.show_all()
        adj.hide()
        self.update()

    def set_fg(self, fg):
        self.ring.fg = self.dots.fg = fg
        self.ring.queue_draw()
        self.dots.queue_draw()

    def update(self):
        f = self.focus
        color = phase_color(f.phase)
        self.ring.color = self.dots.color = color
        self.ring.set_fraction(f.fraction, ms=950 if f.running else 250)
        self.clock.set_text(fmt(f.remaining))
        self.play_glyph.set_glyph("pause" if f.running else "play")
        for phase, b in self.chips.items():
            ctx = b.get_style_context()
            (ctx.add_class if phase == f.phase else ctx.remove_class)("active")
        self.adjust.set_visible(f.phase == "timer" and not f.running)
        rounds = self.focus.cfg["pomo_rounds"]
        self.dots.set_state(f.round_in_cycle, rounds)
        n = f.done_focus
        self.count.set_text(_("{n} focos completos").format(n=n) if n else
                            _("Nenhum foco completo ainda"))
