"""Página "Câmera" da ilha expandida: teste de webcam e de microfone antes de uma chamada.

Nada liga sozinho: a câmera e o microfone só abrem quando você clica, e fecham ao sair da
página ou fechar a ilha. Nada é gravado; cada quadro é desenhado e descartado.
"""
import gi

import cairo

gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo  # noqa: E402

import camtest  # noqa: E402
from i18n import _  # noqa: E402
from icons import Glyph  # noqa: E402
from views import label  # noqa: E402
from widgets import rounded_rect  # noqa: E402


class PreviewArea(Gtk.DrawingArea):
    """Mostra o último quadro (espelhado, como numa videochamada) ou um aviso."""

    def __init__(self):
        super().__init__()
        self.surface = None
        self._data = None            # mantém os bytes vivos enquanto a superfície os usa
        self.message = _("Câmera desligada")
        self.set_size_request(camtest.VIDEO_W, camtest.VIDEO_H)
        self.set_halign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def set_frame(self, data, w, h):
        self._data = bytearray(data)
        self.surface = cairo.ImageSurface.create_for_data(
            self._data, cairo.FORMAT_RGB24, w, h, w * 4)
        self.queue_draw()

    def clear(self, message):
        self.surface, self._data, self.message = None, None, message
        self.queue_draw()

    def _draw(self, _w, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        rounded_rect(cr, 0, 0, w, h, 14)
        cr.clip()
        c = self.get_style_context().get_color(self.get_state_flags())
        if self.surface is not None:
            cr.translate(w, 0)
            cr.scale(-w / self.surface.get_width(), h / self.surface.get_height())
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()
            return
        cr.set_source_rgba(c.red, c.green, c.blue, 0.07)
        cr.paint()
        layout = self.create_pango_layout(self.message)
        tw, th = layout.get_pixel_size()
        cr.set_source_rgba(c.red, c.green, c.blue, 0.55)
        cr.move_to((w - tw) / 2, (h - th) / 2)
        PangoCairo.show_layout(cr, layout)


class LevelBar(Gtk.DrawingArea):
    """Barra de nível do microfone: sobe na hora e desce devagar."""

    def __init__(self):
        super().__init__()
        self.value = 0.0
        self.set_size_request(-1, 12)
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def push(self, fraction):
        self.value = max(fraction, self.value - 0.04)
        self.queue_draw()

    def reset(self):
        self.value = 0.0
        self.queue_draw()

    def _draw(self, _w, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        c = self.get_style_context().get_color(self.get_state_flags())
        cr.set_source_rgba(c.red, c.green, c.blue, 0.14)
        rounded_rect(cr, 0, 0, w, h, h / 2)
        cr.fill()
        if self.value > 0.01:
            # verde -> amarelo -> vermelho conforme o nível
            v = self.value
            color = ((0.30, 0.85, 0.50) if v < 0.6 else (0.98, 0.78, 0.22) if v < 0.85
                     else (0.95, 0.32, 0.30))
            cr.set_source_rgb(*color)
            rounded_rect(cr, 0, 0, max(h, w * v), h, h / 2)
            cr.fill()


class CameraPage(Gtk.Box):
    WIDTH = 420

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        head.pack_start(Glyph("camera", 16), False, False, 0)
        title = label("title")
        title.set_text(_("Câmera e microfone"))
        head.pack_start(title, False, False, 0)
        self.pack_start(head, False, False, 0)

        self.preview = PreviewArea()
        self.pack_start(self.preview, False, False, 0)

        btns = Gtk.Box(spacing=8)
        btns.set_halign(Gtk.Align.CENTER)
        self.cam_btn = self._chip(_("Ligar câmera"), self._toggle_camera)
        self.mic_btn = self._chip(_("Testar microfone"), self._toggle_mic)
        btns.pack_start(self.cam_btn, False, False, 0)
        btns.pack_start(self.mic_btn, False, False, 0)
        self.pack_start(btns, False, False, 0)

        mic = Gtk.Box(spacing=10)
        glyph = Glyph("mic", 16)
        self.level = LevelBar()
        self.db = label("time", 1.0)
        self.db.set_width_chars(7)
        mic.pack_start(glyph, False, False, 0)
        mic.pack_start(self.level, True, True, 0)
        mic.pack_start(self.db, False, False, 0)
        self.pack_start(mic, False, False, 0)

        self.status = label("dim small", 0.5)
        self.status.set_line_wrap(True)
        self.status.set_justify(Gtk.Justification.CENTER)
        self.pack_start(self.status, False, False, 0)

        self.camera = camtest.CameraTest(self._on_frame, self._on_cam_error)
        self.mic = camtest.MicTest(self._on_level, self._on_mic_error)
        self._idle_status()
        if not camtest.HAVE_GST:
            for b in (self.cam_btn, self.mic_btn):
                b.set_sensitive(False)
            self.status.set_text(_("Falta o GStreamer com suporte a PipeWire para testar"))
        self.connect("unmap", lambda *_a: self.stop_all())

    @staticmethod
    def _chip(text, cb):
        b = Gtk.Button(label=text)
        b.set_can_focus(False)
        b.get_style_context().add_class("chip")
        b.connect("clicked", lambda *_a: cb())
        return b

    def _idle_status(self):
        self.status.set_text(_("Só liga quando você clica. Nada é gravado nem guardado."))

    # --- câmera ---------------------------------------------------------------------
    def _toggle_camera(self):
        if self.camera.running:
            self._stop_camera()
        elif self.camera.start():
            self.cam_btn.set_label(_("Desligar câmera"))
            self.cam_btn.get_style_context().add_class("active")
            self.preview.clear(_("Abrindo a câmera…"))
            self.status.set_text(_("Câmera em uso. Feche a ilha ou saia da página para desligar."))

    def _stop_camera(self):
        self.camera.stop()
        self.cam_btn.set_label(_("Ligar câmera"))
        self.cam_btn.get_style_context().remove_class("active")
        self.preview.clear(_("Câmera desligada"))
        if not self.mic.running:
            self._idle_status()

    def _on_frame(self, data, w, h):
        self.preview.set_frame(data, w, h)

    def _on_cam_error(self, message):
        self._stop_camera()
        self.preview.clear(_("Não foi possível abrir a câmera"))
        self.status.set_text(message)

    # --- microfone ------------------------------------------------------------------
    def _toggle_mic(self):
        if self.mic.running:
            self._stop_mic()
        elif self.mic.start():
            self.mic_btn.set_label(_("Parar teste"))
            self.mic_btn.get_style_context().add_class("active")
            self.status.set_text(_("Fale algo: a barra deve se mexer."))

    def _stop_mic(self):
        self.mic.stop()
        self.mic_btn.set_label(_("Testar microfone"))
        self.mic_btn.get_style_context().remove_class("active")
        self.level.reset()
        self.db.set_text("")
        if not self.camera.running:
            self._idle_status()

    def _on_level(self, db):
        self.level.push(camtest.level_fraction(db))
        self.db.set_text(f"{db:.0f} dB" if db > camtest.FLOOR_DB else "")

    def _on_mic_error(self, message):
        self._stop_mic()
        self.status.set_text(message)

    def stop_all(self):
        """Ao sair da página ou fechar a ilha: desliga tudo."""
        if self.camera.running:
            self._stop_camera()
        if self.mic.running:
            self._stop_mic()
