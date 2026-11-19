"""Ícones vetoriais próprios da ilha (traço único, seguem a cor do texto).

Os ícones do tema do sistema mudam de estilo conforme o tema de ícones do usuário; os das
páginas novas são desenhados aqui para ficarem sempre iguais entre si e acompanharem o tema da
ilha. Cada função desenha num quadrado 1×1 (já escalado) com a cor e a espessura do contexto.
"""
import math

from gi.repository import Gtk


def _bell(cr):
    cr.move_to(0.22, 0.70)
    cr.curve_to(0.30, 0.62, 0.28, 0.45, 0.30, 0.38)
    cr.curve_to(0.33, 0.20, 0.67, 0.20, 0.70, 0.38)
    cr.curve_to(0.72, 0.45, 0.70, 0.62, 0.78, 0.70)
    cr.close_path()
    cr.stroke()
    cr.arc(0.5, 0.80, 0.07, 0, math.pi)
    cr.stroke()


def _timer(cr):
    cr.arc(0.5, 0.56, 0.32, 0, 2 * math.pi)
    cr.stroke()
    cr.move_to(0.5, 0.56)
    cr.line_to(0.5, 0.36)
    cr.stroke()
    cr.move_to(0.40, 0.12)
    cr.line_to(0.60, 0.12)
    cr.stroke()


def _tasks(cr):
    for i, y in enumerate((0.26, 0.5, 0.74)):
        cr.move_to(0.18, y)
        cr.line_to(0.26, y + 0.07)
        cr.line_to(0.36, y - 0.07)
        cr.stroke()
        cr.move_to(0.48, y)
        cr.line_to(0.84, y)
        cr.stroke()


def _sun(cr):
    cr.arc(0.5, 0.5, 0.17, 0, 2 * math.pi)
    cr.stroke()
    for k in range(8):
        a = k * math.pi / 4
        cr.move_to(0.5 + 0.27 * math.cos(a), 0.5 + 0.27 * math.sin(a))
        cr.line_to(0.5 + 0.38 * math.cos(a), 0.5 + 0.38 * math.sin(a))
        cr.stroke()


def _speaker(cr):
    cr.move_to(0.16, 0.40)
    cr.line_to(0.32, 0.40)
    cr.line_to(0.50, 0.24)
    cr.line_to(0.50, 0.76)
    cr.line_to(0.32, 0.60)
    cr.line_to(0.16, 0.60)
    cr.close_path()
    cr.stroke()
    cr.arc(0.50, 0.5, 0.17, -math.pi / 3, math.pi / 3)
    cr.stroke()
    cr.arc(0.50, 0.5, 0.31, -math.pi / 3, math.pi / 3)
    cr.stroke()


def _muted(cr):
    _speaker_body(cr)
    cr.move_to(0.64, 0.38)
    cr.line_to(0.84, 0.62)
    cr.move_to(0.84, 0.38)
    cr.line_to(0.64, 0.62)
    cr.stroke()


def _speaker_body(cr):
    cr.move_to(0.14, 0.40)
    cr.line_to(0.30, 0.40)
    cr.line_to(0.48, 0.24)
    cr.line_to(0.48, 0.76)
    cr.line_to(0.30, 0.60)
    cr.line_to(0.14, 0.60)
    cr.close_path()
    cr.stroke()


def _wifi(cr):
    for r in (0.14, 0.27, 0.40):
        cr.arc(0.5, 0.78, r, -math.pi * 0.80, -math.pi * 0.20)
        cr.stroke()
    cr.arc(0.5, 0.78, 0.03, 0, 2 * math.pi)
    cr.fill()


def _ethernet(cr):
    cr.rectangle(0.20, 0.22, 0.60, 0.40)
    cr.stroke()
    for x in (0.34, 0.50, 0.66):
        cr.move_to(x, 0.22)
        cr.line_to(x, 0.38)
        cr.stroke()
    cr.move_to(0.5, 0.62)
    cr.line_to(0.5, 0.80)
    cr.move_to(0.30, 0.80)
    cr.line_to(0.70, 0.80)
    cr.stroke()


def _vpn(cr):
    cr.move_to(0.5, 0.14)
    cr.line_to(0.80, 0.26)
    cr.line_to(0.80, 0.52)
    cr.curve_to(0.80, 0.70, 0.64, 0.82, 0.5, 0.88)
    cr.curve_to(0.36, 0.82, 0.20, 0.70, 0.20, 0.52)
    cr.line_to(0.20, 0.26)
    cr.close_path()
    cr.stroke()


def _battery(cr):
    cr.rectangle(0.14, 0.32, 0.64, 0.36)
    cr.stroke()
    cr.rectangle(0.82, 0.42, 0.05, 0.16)
    cr.fill()
    cr.rectangle(0.20, 0.38, 0.30, 0.24)
    cr.fill()


def _trash(cr):
    cr.move_to(0.22, 0.28)
    cr.line_to(0.78, 0.28)
    cr.move_to(0.40, 0.28)
    cr.line_to(0.40, 0.18)
    cr.line_to(0.60, 0.18)
    cr.line_to(0.60, 0.28)
    cr.stroke()
    cr.move_to(0.28, 0.28)
    cr.line_to(0.32, 0.82)
    cr.line_to(0.68, 0.82)
    cr.line_to(0.72, 0.28)
    cr.stroke()


def _plus(cr):
    cr.move_to(0.5, 0.2)
    cr.line_to(0.5, 0.8)
    cr.move_to(0.2, 0.5)
    cr.line_to(0.8, 0.5)
    cr.stroke()


def _check(cr):
    cr.move_to(0.22, 0.52)
    cr.line_to(0.42, 0.72)
    cr.line_to(0.80, 0.28)
    cr.stroke()


def _play(cr):
    cr.move_to(0.32, 0.20)
    cr.line_to(0.80, 0.50)
    cr.line_to(0.32, 0.80)
    cr.close_path()
    cr.fill()


def _pause(cr):
    cr.rectangle(0.26, 0.20, 0.16, 0.60)
    cr.rectangle(0.58, 0.20, 0.16, 0.60)
    cr.fill()


def _reset(cr):
    cr.arc(0.5, 0.5, 0.30, math.pi * 0.15, math.pi * 1.80)
    cr.stroke()
    cr.move_to(0.74, 0.12)
    cr.line_to(0.78, 0.34)
    cr.line_to(0.56, 0.32)
    cr.stroke()


def _skip(cr):
    cr.move_to(0.24, 0.22)
    cr.line_to(0.64, 0.50)
    cr.line_to(0.24, 0.78)
    cr.close_path()
    cr.fill()
    cr.rectangle(0.70, 0.22, 0.10, 0.56)
    cr.fill()


def _arrow_down(cr):
    cr.move_to(0.5, 0.2)
    cr.line_to(0.5, 0.78)
    cr.move_to(0.28, 0.58)
    cr.line_to(0.5, 0.80)
    cr.line_to(0.72, 0.58)
    cr.stroke()


def _arrow_up(cr):
    cr.move_to(0.5, 0.8)
    cr.line_to(0.5, 0.22)
    cr.move_to(0.28, 0.42)
    cr.line_to(0.5, 0.20)
    cr.line_to(0.72, 0.42)
    cr.stroke()


def _chevron_left(cr):
    cr.move_to(0.62, 0.22)
    cr.line_to(0.34, 0.5)
    cr.line_to(0.62, 0.78)
    cr.stroke()


def _chevron_right(cr):
    cr.move_to(0.38, 0.22)
    cr.line_to(0.66, 0.5)
    cr.line_to(0.38, 0.78)
    cr.stroke()


def _terminal(cr):
    cr.rectangle(0.12, 0.2, 0.76, 0.6)
    cr.stroke()
    cr.move_to(0.26, 0.40)
    cr.line_to(0.40, 0.50)
    cr.line_to(0.26, 0.60)
    cr.move_to(0.48, 0.62)
    cr.line_to(0.66, 0.62)
    cr.stroke()


def _win_min(cr):
    cr.move_to(0.25, 0.62)
    cr.line_to(0.75, 0.62)
    cr.stroke()


def _win_max(cr):
    cr.rectangle(0.26, 0.26, 0.48, 0.48)
    cr.stroke()


def _win_restore(cr):
    cr.rectangle(0.22, 0.34, 0.40, 0.40)
    cr.stroke()
    cr.move_to(0.38, 0.34)
    cr.line_to(0.38, 0.24)
    cr.line_to(0.78, 0.24)
    cr.line_to(0.78, 0.62)
    cr.line_to(0.62, 0.62)
    cr.stroke()


def _win_close(cr):
    cr.move_to(0.27, 0.27)
    cr.line_to(0.73, 0.73)
    cr.move_to(0.73, 0.27)
    cr.line_to(0.27, 0.73)
    cr.stroke()


def _mic(cr):
    cr.new_sub_path()
    cr.arc(0.5, 0.30, 0.13, math.pi, 2 * math.pi)
    cr.line_to(0.63, 0.46)
    cr.arc(0.5, 0.46, 0.13, 0, math.pi)
    cr.close_path()
    cr.fill()
    cr.arc(0.5, 0.46, 0.25, 0, math.pi)
    cr.stroke()
    cr.move_to(0.5, 0.71)
    cr.line_to(0.5, 0.84)
    cr.move_to(0.36, 0.84)
    cr.line_to(0.64, 0.84)
    cr.stroke()


def _camera(cr):
    cr.rectangle(0.12, 0.30, 0.50, 0.40)
    cr.fill()
    cr.move_to(0.66, 0.46)
    cr.line_to(0.88, 0.32)
    cr.line_to(0.88, 0.68)
    cr.line_to(0.66, 0.54)
    cr.close_path()
    cr.fill()


def _bluetooth(cr):
    cr.move_to(0.30, 0.35)
    cr.line_to(0.70, 0.68)
    cr.line_to(0.50, 0.86)
    cr.line_to(0.50, 0.14)
    cr.line_to(0.70, 0.32)
    cr.line_to(0.30, 0.65)
    cr.stroke()


def _moon(cr):
    cr.arc(0.5, 0.5, 0.32, math.pi * 0.35, math.pi * 1.65)
    cr.arc_negative(0.62, 0.40, 0.26, math.pi * 1.45, math.pi * 0.55)
    cr.close_path()
    cr.stroke()


GLYPHS = {
    "bell": _bell, "timer": _timer, "tasks": _tasks, "sun": _sun, "speaker": _speaker,
    "muted": _muted, "wifi": _wifi, "ethernet": _ethernet, "vpn": _vpn, "battery": _battery,
    "trash": _trash, "plus": _plus, "check": _check, "play": _play, "pause": _pause,
    "reset": _reset, "skip": _skip, "down": _arrow_down, "up": _arrow_up, "moon": _moon,
    "win_min": _win_min, "win_max": _win_max, "win_restore": _win_restore,
    "win_close": _win_close, "bluetooth": _bluetooth, "mic": _mic, "camera": _camera, "terminal": _terminal, "left": _chevron_left, "right": _chevron_right,
}


class Glyph(Gtk.DrawingArea):
    """Ícone desenhado; `fg` é a cor (r, g, b) e `alpha` a opacidade."""

    def __init__(self, name, size=16, alpha=1.0):
        super().__init__()
        self.name, self.size, self.alpha = name, size, alpha
        self.fg, self.fixed = (1, 1, 1), False
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def set_glyph(self, name):
        if name != self.name:
            self.name = name
            self.queue_draw()

    def set_color(self, rgb):
        """Fixa uma cor (ex.: o laranja do Claude); None volta a seguir o tema."""
        self.fixed = rgb is not None
        if rgb is not None:
            self.fg = rgb
        self.queue_draw()

    def _draw(self, _w, cr):
        s = min(self.get_allocated_width(), self.get_allocated_height())
        cr.translate((self.get_allocated_width() - s) / 2, (self.get_allocated_height() - s) / 2)
        cr.scale(s, s)
        # segue a cor `color` do CSS (o tema da ilha); `fg` só vale se for fixado de propósito
        c = self.get_style_context().get_color(self.get_state_flags())
        rgb = self.fg if self.fixed else (c.red, c.green, c.blue)
        cr.set_source_rgba(*rgb, self.alpha * (1.0 if self.fixed else c.alpha))
        cr.set_line_width(max(1.2, s / 9) / s)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        GLYPHS.get(self.name, _plus)(cr)


def glyph_button(name, size, cb, tooltip=None):
    """Botão redondo com um Glyph dentro (mesma classe `control` dos botões do player)."""
    btn = Gtk.Button()
    g = Glyph(name, size)
    btn.add(g)
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_can_focus(False)
    btn.get_style_context().add_class("control")
    if tooltip:
        btn.set_tooltip_text(tooltip)
    btn.connect("clicked", lambda *_a: cb())
    return btn, g
