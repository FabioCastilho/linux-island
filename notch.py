"""Estilo "entalhe": a ilha colada na borda do topo, com as quinas de cima côncavas.

O fundo deixa de ser CSS e passa a ser desenhado com cairo, porque o CSS não faz canto
invertido. A forma é um retângulo de cantos de baixo arredondados mais duas "orelhas"
(filetes côncavos) que ligam o topo da ilha à borda da tela, como o entalhe de um notebook.

Mixin da janela Island; usa self.cfg, self.shell, self.expanded dela.
"""
import math

import cairo
from gi.repository import GLib

from config import rgba
from blur import Blur
from widgets import rounded_rect

EAR = 12         # padrão do raio dos filetes côncavos de cima (config "notch_ear")
COMPACT_R = 14   # padrão do raio dos cantos de baixo com a ilha fechada ("radius_compact")


def notch_path(cr, x, w, h, ear, r, outline=False):
    """Contorno do entalhe: x/w = corpo da ilha; as orelhas ocupam `ear` px de cada lado."""
    r = min(r, h - ear, w / 2)
    left, right = x, x + w
    if outline:  # só as laterais e a base: sem a linha em cima, para não riscar a borda da tela
        cr.move_to(right + ear, 0)
    else:
        cr.move_to(left - ear, 0)
        cr.line_to(right + ear, 0)
    cr.arc_negative(right + ear, ear, ear, -math.pi / 2, -math.pi)   # orelha direita
    cr.line_to(right, h - r)
    cr.arc(right - r, h - r, r, 0, math.pi / 2)                       # canto inferior dir.
    cr.line_to(left + r, h)
    cr.arc(left + r, h - r, r, math.pi / 2, math.pi)                  # canto inferior esq.
    cr.line_to(left, ear)
    cr.arc_negative(left - ear, ear, ear, 0, -math.pi / 2)            # orelha esquerda
    if not outline:
        cr.close_path()


class NotchMixin:
    """Desenha o fundo da ilha com cairo: entalhe (quinas côncavas) e/ou vidro."""

    _notch = False  # o _apply() roda antes do _notch_init()
    _drawn = False

    _blur = None
    _blur_timer = None

    def _notch_init(self):
        self.connect("draw", self._notch_draw)
        self.connect("map", self._blur_setup)
        self.connect("unmap", self._blur_unmap)
        if self.get_mapped():  # a janela já abriu antes deste init
            self._blur_setup()
        self.shell.connect("size-allocate", lambda *_a: (self.queue_draw(), self._blur_sync()))

    # --- desfoque do compositor ---------------------------------------------
    def _blur_setup(self, *_a):
        """A superfície Wayland muda a cada remapeamento: liga o desfoque de novo, mas só
        depois que ela assentar (pedir dentro do evento 'map' corria contra o configure)."""
        self._blur = None
        if self._blur_timer:
            GLib.source_remove(self._blur_timer)
        self._blur_timer = GLib.timeout_add(250, self._blur_attach, self.get_window())

    def _blur_unmap(self, *_a):
        if self._blur_timer:
            GLib.source_remove(self._blur_timer)
            self._blur_timer = None
        self._blur = None  # a superfície some junto: os proxies antigos não servem mais

    def _blur_attach(self, gdk_window):
        self._blur_timer = None
        if not self.get_mapped() or self.get_window() is not gdk_window:
            return False  # remapeou de novo nesse meio tempo: o novo map cuida disso
        blur = Blur()
        try:
            blur.attach(self.get_display(), gdk_window)
        except Exception:  # nunca derruba a ilha por causa do efeito
            blur.available = False
        from pointer import log
        log("blur disponível:", blur.available)
        self._blur = blur
        self._blur_sync()
        return False

    def _blur_sync(self):
        b = self._blur
        if b is None or not b.available:
            return
        if self.cfg["glass_style"] and self.cfg["glass_blur"]:
            a = self.shell.get_allocation()
            ear = self._ear() if self._notch else 0
            r = self.cfg["radius_expanded"] if self.expanded else self.cfg["radius_compact"]
            b.set_shape(a.width + 2 * ear, a.height, r, ear)
            self.queue_draw()  # o pedido só vale no próximo commit da superfície
        else:
            b.clear()
            self.queue_draw()

    def _notch_apply(self):
        """Liga/desliga o entalhe e o vidro (o CSS larga o fundo quando o cairo desenha)."""
        notch, drawn = bool(self.cfg["notch_style"]), bool(
            self.cfg["notch_style"] or self.cfg["glass_style"])
        ctx = self.shell.get_style_context()
        (ctx.add_class if drawn else ctx.remove_class)("drawn")
        side = self._ear() if notch else 0
        if notch != self._notch or self.shell.get_margin_start() != side:
            self._notch = notch
            # a margem lateral comporta as orelhas: muda junto com o tamanho delas
            self.shell.set_margin_start(side)
            self.shell.set_margin_end(side)
            self._follow_size()
        self._drawn = drawn
        self.queue_draw()
        self._blur_sync()

    def _ear(self):
        return self.cfg["notch_ear"]

    def _top_margin(self):
        return 0 if self._notch else self.cfg["margin_top"]

    def _path(self, cr, outline=False):
        a = self.shell.get_allocation()
        r = self.cfg["radius_expanded"] if self.expanded else self.cfg["radius_compact"]
        if self._notch:
            notch_path(cr, a.x, a.width, a.height, self._ear(), r, outline)
        else:
            rounded_rect(cr, a.x + 0.5, a.y + 0.5, a.width - 1, a.height - 1,
                         min(r, a.height / 2))
        return a

    def _notch_draw(self, _w, cr):
        if not self._drawn:
            return False
        c = rgba(self.cfg["bg_color"])
        a = self._path(cr)
        cr.set_source_rgba(c.red, c.green, c.blue, c.alpha)
        cr.fill_preserve() if self.cfg["glass_style"] else cr.fill()
        if self.cfg["glass_style"]:
            # brilho especular: luz entrando pelo topo, sumindo antes da metade
            cr.save()
            cr.clip()
            sheen = cairo.LinearGradient(0, a.y, 0, a.y + a.height)
            sheen.add_color_stop_rgba(0.0, 1, 1, 1, 0.20)
            sheen.add_color_stop_rgba(0.45, 1, 1, 1, 0.04)
            sheen.add_color_stop_rgba(1.0, 1, 1, 1, 0.0)
            cr.set_source(sheen)
            cr.paint()
            cr.restore()
            # aro de luz: forte em cima, suave no meio, de novo um pouco embaixo
            self._path(cr, outline=True)
            rim = cairo.LinearGradient(0, a.y, 0, a.y + a.height)
            rim.add_color_stop_rgba(0.0, 1, 1, 1, 0.55)
            rim.add_color_stop_rgba(0.5, 1, 1, 1, 0.10)
            rim.add_color_stop_rgba(1.0, 1, 1, 1, 0.28)
            cr.set_source(rim)
            cr.set_line_width(1.0)
            cr.stroke()
        return False  # segue para o desenho normal (os filhos vão por cima)
