"""O Clawd (mascote em pixel art) animado: os quadros ficam em assets/clawd/."""
import os

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "clawd")
SRC_W, SRC_H = 160, 125  # tamanho dos quadros originais


def _frames(prefix, first, last):
    return [f"{prefix}{i}" for i in range(first, last + 1)]


# animação -> (quadros por segundo, quadros)
ANIMS = {
    "idle": (4.0, _frames("f", 0, 7)),     # parado, respirando
    "busy": (6.0, _frames("h", 0, 7)),     # programando no notebook
    "alert": (5.0, _frames("f", 25, 30)),  # precisa de você
    "done": (5.0, _frames("h", 16, 23)),   # terminou: comemora
    "sleep": (1.5, _frames("g", 24, 30)),  # parado há muito tempo: dorme
}

_cache = {}  # (quadro, largura) -> GdkPixbuf


def frame_path(name):
    return os.path.join(DIR, f"{name}.png")


def frame(name, width):
    """Quadro `name` redimensionado para `width` px de largura (mantém a proporção)."""
    key = (name, width)
    if key not in _cache:
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(frame_path(name))
            height = max(1, round(width * pb.get_height() / pb.get_width()))
            _cache[key] = pb.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        except GLib.Error:
            _cache[key] = None  # quadro ausente: o desenho só fica vazio
    return _cache[key]


class SpriteView(Gtk.DrawingArea):
    """Mostra uma animação do Clawd. Só anima enquanto está visível (o timer liga no map)."""

    def __init__(self, width, anim="idle"):
        super().__init__()
        self.width = width
        self.height = round(width * SRC_H / SRC_W)
        self.set_size_request(width, self.height)
        self.anim = anim if anim in ANIMS else "idle"
        self._i = 0
        self._timer = None
        self.connect("draw", self._draw)
        self.connect("map", lambda *_a: self._start())
        self.connect("unmap", lambda *_a: self._stop())

    def set_anim(self, name):
        name = name if name in ANIMS else "idle"
        if name == self.anim:
            return
        self.anim, self._i = name, 0
        if self._timer is not None:  # o ritmo (fps) muda de uma animação para outra
            self._stop()
            self._start()
        self.queue_draw()

    def _start(self):
        if self._timer is None:
            fps = ANIMS[self.anim][0]
            self._timer = GLib.timeout_add(int(1000 / fps), self._next)

    def _stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _next(self):
        self._i += 1
        self.queue_draw()
        return True

    def current(self):
        names = ANIMS[self.anim][1]
        return names[self._i % len(names)]

    def _draw(self, _w, cr):
        pb = frame(self.current(), self.width)
        if pb is None:
            return
        w, h = self.get_allocated_width(), self.get_allocated_height()
        Gdk.cairo_set_source_pixbuf(cr, pb, (w - pb.get_width()) / 2, h - pb.get_height())
        cr.paint()
