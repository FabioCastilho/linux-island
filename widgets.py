"""Widgets desenhados com cairo: capa arredondada, equalizador e barra de progresso."""
import math
import time

from gi.repository import Gdk, GdkPixbuf, Gtk

DEFAULT_ACCENT = (0.12, 0.84, 0.38)  # verde Spotify
EQ_STYLES = ("bars", "wave", "dots", "mirror", "pulse")
GLOW_PAD = 8  # espaço em volta da capa para o brilho


def rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def accent_from_pixbuf(pb):
    """Cor de destaque: média da capa, clareada para ler bem sobre preto."""
    if pb is None:
        return DEFAULT_ACCENT
    tiny = pb.scale_simple(1, 1, GdkPixbuf.InterpType.BILINEAR)
    r, g, b = (c / 255 for c in tiny.get_pixels()[:3])
    mx = max(r, g, b, 1e-3)
    if mx < 0.55:  # capas escuras: puxa o brilho para cima
        k = 0.55 / mx
        r, g, b = min(r * k, 1), min(g * k, 1), min(b * k, 1)
    return (r, g, b)


class Art(Gtk.DrawingArea):
    def __init__(self, size, radius):
        super().__init__()
        self.size, self.radius = size, radius
        self.pixbuf = None
        self.glow = None  # (r, g, b) ou None; só a capa grande usa
        self._pad = 0
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def set_glow(self, color):
        """Brilho suave da cor de destaque em volta da capa (None desliga)."""
        pad = GLOW_PAD if color else 0
        self.glow = color
        if pad != self._pad:
            self._pad = pad
            self.set_size_request(self.size + 2 * pad, self.size + 2 * pad)
        self.queue_draw()

    def set_source(self, original):
        self.pixbuf = (original.scale_simple(self.size * 2, self.size * 2,
                                             GdkPixbuf.InterpType.BILINEAR)
                       if original else None)
        self.queue_draw()

    def _draw(self, _w, cr):
        s = self.size
        pad = self._pad
        if pad and self.glow:
            for i in range(pad, 0, -1):  # camadas de fora para dentro, cada vez mais fortes
                cr.set_source_rgba(*self.glow, 0.20 * (1 - i / pad) ** 2)
                rounded_rect(cr, pad - i, pad - i, s + 2 * i, s + 2 * i, self.radius + i)
                cr.fill()
        cr.translate(pad, pad)
        rounded_rect(cr, 0, 0, s, s, self.radius)
        cr.clip()
        if self.pixbuf:
            cr.scale(0.5, 0.5)
            Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
            cr.paint()
        else:
            cr.set_source_rgb(0.18, 0.18, 0.18)
            cr.paint()
            cr.set_source_rgb(*DEFAULT_ACCENT)
            cr.arc(s / 2, s / 2, s / 6, 0, 2 * math.pi)
            cr.fill()


class Equalizer(Gtk.DrawingArea):
    """Barrinhas animadas enquanto toca; paradas e baixas em pausa."""

    BARS = 4

    def __init__(self, w=18, h=14):
        super().__init__()
        self.w, self.h = w, h
        self.accent = DEFAULT_ACCENT
        self.playing = False
        self._tick = None
        self.set_size_request(w, h)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def set_playing(self, playing):
        self.playing = playing
        if playing and self._tick is None:
            self._tick = self.add_tick_callback(self._on_tick)
        elif not playing and self._tick is not None:
            self.remove_tick_callback(self._tick)
            self._tick = None
        self.queue_draw()

    _last_frame = 0

    def _on_tick(self, _w, clock):
        """Anima a ~24 quadros/s: a 60 o redesenho da janela inteira custava CPU à toa."""
        now = clock.get_frame_time()
        if now - self._last_frame >= 41_000:
            self._last_frame = now
            self.queue_draw()
        return True

    style = "bars"

    def set_style(self, style):
        self.style = style if style in EQ_STYLES else "bars"
        self.queue_draw()

    def _draw(self, _w, cr):
        getattr(self, f"_draw_{self.style}")(cr, time.monotonic())

    def _draw_bars(self, cr, t):
        gap = 2
        bw = (self.w - gap * (self.BARS - 1)) / self.BARS
        cr.set_source_rgb(*self.accent)
        for i in range(self.BARS):
            if self.playing:
                lvl = 0.35 + 0.65 * abs(math.sin(t * (3.1 + i * 1.7) + i * 1.3))
            else:
                lvl = 0.22
            bh = max(bw, self.h * lvl)
            rounded_rect(cr, i * (bw + gap), (self.h - bh) / 2, bw, bh, bw / 2)
            cr.fill()

    def _draw_mirror(self, cr, t):
        """Mais barras, simétricas a partir do centro (visual de espectro)."""
        n = max(5, int(self.w / 3.4) | 1)  # ímpar: tem uma barra central
        gap = 1.4
        bw = (self.w - gap * (n - 1)) / n
        mid = n // 2
        cr.set_source_rgb(*self.accent)
        for i in range(n):
            d = abs(i - mid)  # o lado esquerdo espelha o direito
            if self.playing:
                lvl = (0.30 + 0.70 * abs(math.sin(t * (2.6 + d * 0.9) + d * 1.1))) \
                    * (1.0 - 0.45 * d / max(1, mid))
            else:
                lvl = 0.18
            bh = max(bw, self.h * lvl)
            rounded_rect(cr, i * (bw + gap), (self.h - bh) / 2, bw, bh, bw / 2)
            cr.fill()

    def _draw_wave(self, cr, t):
        """Uma onda que corre na horizontal; parada, vira uma linha reta."""
        amp = (self.h / 2 - 1.5) * (0.45 + 0.55 * abs(math.sin(t * 2.1))) if self.playing else 0.0
        cr.set_source_rgb(*self.accent)
        cr.set_line_width(max(1.4, self.h / 9))
        cr.set_line_cap(1)
        steps = max(12, int(self.w))
        for k in range(steps + 1):
            x = 1 + (self.w - 2) * k / steps
            edge = math.sin(math.pi * k / steps)  # afina as pontas
            y = self.h / 2 + amp * edge * math.sin(k / steps * 2 * math.pi * 1.5 - t * 6.5)
            (cr.move_to if k == 0 else cr.line_to)(x, y)
        cr.stroke()

    def _draw_dots(self, cr, t):
        n = 4
        r = max(1.3, min(self.w / (n * 2.6), self.h / 4))
        step = (self.w - 2 * r) / (n - 1)
        cr.set_source_rgb(*self.accent)
        for i in range(n):
            lift = abs(math.sin(t * 4.2 + i * 0.85)) if self.playing else 0.0
            y = self.h - r - lift * (self.h - 2 * r)
            cr.arc(r + i * step, y if self.playing else self.h / 2, r, 0, 2 * math.pi)
            cr.fill()

    def _draw_pulse(self, cr, t):
        """Um ponto com ondas que se abrem a partir dele."""
        cx, cy = self.w / 2, self.h / 2
        core = max(1.8, self.h / 5)
        cr.set_source_rgb(*self.accent)
        cr.arc(cx, cy, core * (1 + 0.12 * math.sin(t * 5) if self.playing else 1), 0, 2 * math.pi)
        cr.fill()
        if not self.playing:
            return
        reach = min(self.w, self.h) / 2 - 0.5
        for k in (0.0, 0.5):
            ph = (t * 0.9 + k) % 1.0
            cr.set_source_rgba(*self.accent, 0.9 * (1 - ph))
            cr.set_line_width(1.4)
            cr.arc(cx, cy, core + ph * max(0.0, reach - core), 0, 2 * math.pi)
            cr.stroke()


class Progress(Gtk.DrawingArea):
    """Barra de progresso clicável/arrastável. on_seek(fração)."""

    def __init__(self, on_seek, height=16, live=False):
        super().__init__()
        self.on_seek = on_seek
        self.live = live  # chama on_seek enquanto arrasta (ex.: volume)
        self.fraction = 0.0
        self.accent = DEFAULT_ACCENT
        self.fg = (1, 1, 1)
        self._drag = None
        self._hover = False
        self.set_size_request(-1, height)
        self.set_hexpand(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK
                        | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("motion-notify-event", self._motion)
        self.connect("button-release-event", self._release)
        self.connect("enter-notify-event", lambda *_a: self._set_hover(True))
        self.connect("leave-notify-event", lambda *_a: self._set_hover(False))

    def _set_hover(self, v):
        self._hover = v
        self.queue_draw()

    def set_fraction(self, f):
        if self._drag is None:
            self.fraction = max(0.0, min(1.0, f))
            self.queue_draw()

    def _frac_at(self, x):
        return max(0.0, min(1.0, x / max(1, self.get_allocated_width())))

    def _press(self, _w, ev):
        if ev.button == 1:
            self._drag = self._frac_at(ev.x)
            if self.live:
                self.on_seek(self._drag)
            self.queue_draw()
        return True

    def _motion(self, _w, ev):
        if self._drag is not None:
            self._drag = self._frac_at(ev.x)
            if self.live:
                self.on_seek(self._drag)
            self.queue_draw()
        return True

    def _release(self, _w, ev):
        if self._drag is not None:
            self.fraction = self._drag
            self._drag = None
            self.on_seek(self.fraction)
            self.queue_draw()
        return True

    def _draw(self, _w, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        active = self._hover or self._drag is not None
        th = 6 if active else 4
        y = (h - th) / 2
        f = self._drag if self._drag is not None else self.fraction
        cr.set_source_rgba(*self.fg, 0.18)
        rounded_rect(cr, 0, y, w, th, th / 2)
        cr.fill()
        if f > 0:
            cr.set_source_rgb(*self.accent)
            rounded_rect(cr, 0, y, max(th, w * f), th, th / 2)
            cr.fill()
        if active:
            cr.set_source_rgb(*self.fg)
            cr.arc(min(max(w * f, 6), w - 6), h / 2, 6, 0, 2 * math.pi)
            cr.fill()


def load_color(u):
    """Verde → amarelo → vermelho conforme a carga (0..1)."""
    stops = [(0.0, (0.30, 0.85, 0.50)), (0.55, (0.98, 0.78, 0.22)), (1.0, (0.95, 0.32, 0.30))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if u <= b:
            t = (u - a) / (b - a)
            return tuple(x + (y - x) * t for x, y in zip(ca, cb))
    return stops[-1][1]


class Tweened:
    """Mixin para widgets com `.fraction`: set_fraction() desliza até o valor novo."""

    def _tween_init(self):
        self.fraction = 0.0
        self._from = self._to = 0.0
        self._t0 = None
        self._tween_id = None

    def set_fraction(self, f, ms=450):
        f = max(0.0, min(1.0, f))
        if f == self._to:
            return
        self._from, self._to = self.fraction, f
        self._t0 = time.monotonic()
        self._ms = ms
        if self._tween_id is None:
            self._tween_id = self.add_tick_callback(self._tween_step)

    def _tween_step(self, *_a):
        t = min(1.0, (time.monotonic() - self._t0) * 1000 / self._ms)
        e = 1 - (1 - t) ** 3  # ease-out cúbico
        self.fraction = self._from + (self._to - self._from) * e
        self.queue_draw()
        if t >= 1.0:
            self._tween_id = None
            return False
        return True


class MiniRing(Tweened, Gtk.DrawingArea):
    """Anel pequeno de carga para a pílula, com a cor seguindo o valor."""

    def __init__(self, size=14, width=2.6):
        super().__init__()
        self._tween_init()
        self.size, self.width = size, width
        self.fg = (1, 1, 1)
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        c = self.size / 2
        r = c - self.width / 2
        cr.set_line_width(self.width)
        cr.set_source_rgba(*self.fg, 0.18)
        cr.arc(c, c, r, 0, 2 * math.pi)
        cr.stroke()
        if self.fraction > 0.01:
            cr.set_line_cap(1)
            cr.set_source_rgb(*load_color(self._to))
            cr.arc(c, c, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * self.fraction)
            cr.stroke()


class CupIcon(Gtk.DrawingArea):
    """Xícara com vapor: aparece na pílula quando o PC está sendo mantido acordado."""

    def __init__(self, size=14):
        super().__init__()
        self.fg = (1, 1, 1)
        self.set_size_request(size, size)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        s = self.get_allocated_width()
        cr.set_source_rgb(*self.fg)
        cr.set_line_width(max(1.1, s / 11))
        cr.set_line_cap(1)
        for dx in (0.34, 0.54):  # vapor
            cr.move_to(s * dx, s * 0.30)
            cr.curve_to(s * (dx - 0.07), s * 0.20, s * (dx + 0.07), s * 0.12, s * dx, s * 0.02)
            cr.stroke()
        rounded_rect(cr, s * 0.14, s * 0.42, s * 0.56, s * 0.46, s * 0.14)  # copo
        cr.fill()
        cr.arc(s * 0.74, s * 0.60, s * 0.15, -math.pi / 2, math.pi / 2)  # alça
        cr.stroke()
