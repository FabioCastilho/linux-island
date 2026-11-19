"""Teste de câmera e de microfone: vídeo e nível de áudio ao vivo, só enquanto você pede.

Usa o GStreamer com o `pipewiresrc` (o mesmo caminho que os navegadores usam). Nada é gravado
nem guardado: cada quadro é desenhado e descartado, e o áudio vira só um número (o nível).
A câmera e o microfone ligam quando `start()` é chamado e desligam em `stop()`.
"""
import array
import math
import time

import gi

try:
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    HAVE_GST = Gst.ElementFactory.find("pipewiresrc") is not None
except (ValueError, ImportError):
    Gst, HAVE_GST = None, False

from gi.repository import GLib  # noqa: E402

from logutil import warn  # noqa: E402

VIDEO_W, VIDEO_H = 384, 216
VIDEO_FPS = 15
SINK = "appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false"
# A câmera precisa de um modo concreto: deixar o pipewiresrc escolher sozinho falha em várias.
# Tenta-se uma lista de modos pequenos e comuns até um abrir; a saída tem sempre o mesmo tamanho
# (com bordas pretas se a proporção for outra).
VIDEO_MODES = ("width=640,height=480", "width=1280,height=720", "width=640,height=360",
               "width=320,height=240", "width=1024,height=576")
VIDEO_PIPES = [
    f"pipewiresrc ! video/x-raw,{mode} ! videoconvert ! videoscale add-borders=true ! "
    f"video/x-raw,format=BGRx,width={VIDEO_W},height={VIDEO_H} ! {SINK}"
    for mode in VIDEO_MODES]
AUDIO_PIPES = [
    "pipewiresrc ! audio/x-raw ! audioconvert ! audioresample ! "
    "audio/x-raw,format=S16LE,channels=1,rate=16000 ! "
    "appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"]
FLOOR_DB = -60.0


def level_db(data):
    """Nível (dBFS, 0 = máximo) de amostras de 16 bits (bytes). Silêncio = FLOOR_DB."""
    n = len(data) // 2
    if n == 0:
        return FLOOR_DB
    samples = array.array("h")
    samples.frombytes(data[:n * 2])
    rms = math.sqrt(sum(s * s for s in samples) / n)
    if rms < 1:
        return FLOOR_DB
    return max(FLOOR_DB, 20 * math.log10(rms / 32768))


def level_fraction(db):
    """dBFS -> 0..1 para a barra (−60 dB vazio, 0 dB cheio)."""
    return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB))


class _Stream:
    """Um pipeline que entrega amostras para `on_sample(dados, largura, altura)` na thread da UI.

    `pipelines` é uma lista de alternativas: se a primeira não abre (modo não aceito pela
    câmera), tenta a seguinte sem avisar; só reclama quando todas falharam."""

    def __init__(self, pipelines, on_sample, on_error, min_interval=0.0):
        self.pipelines, self.on_sample, self.on_error = pipelines, on_sample, on_error
        self.min_interval = min_interval
        self.pipeline = None
        self.running = False
        self._index = 0
        self._got_sample = False
        self._last = 0.0

    def start(self):
        if self.running:
            return True
        if not HAVE_GST:
            self.on_error("GStreamer com PipeWire não está instalado")
            return False
        self.running, self._got_sample, self._last = True, False, 0.0
        return self._launch(0)

    def _launch(self, index):
        self._index = index
        try:
            self.pipeline = Gst.parse_launch(self.pipelines[index])
        except GLib.Error as e:
            warn("pipeline de teste inválido", e)
            return self._fail("Não deu para montar o teste")
        self.pipeline.get_by_name("sink").connect("new-sample", self._new_sample)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._bus_error)
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            return self._next_or_fail("Não deu para abrir o dispositivo")
        return True

    def _teardown(self):
        if self.pipeline is not None:
            self.pipeline.get_bus().remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

    def stop(self):
        self.running = False
        self._teardown()

    def _fail(self, message):
        self.stop()
        self.on_error(message)
        return False

    def _next_or_fail(self, message):
        """Antes de desistir, tenta o próximo modo (só se ainda não chegou nenhum quadro)."""
        if not self._got_sample and self._index + 1 < len(self.pipelines):
            self._teardown()
            GLib.idle_add(self._retry, self._index + 1)
            return True
        return self._fail(message)

    def _retry(self, index):
        if self.running:
            self._launch(index)
        return False

    def _new_sample(self, sink):
        # thread de streaming do GStreamer: copia o que precisa e entrega à UI
        sample = sink.emit("pull-sample")
        if sample is None or not self.running:
            return Gst.FlowReturn.OK
        now = time.monotonic()
        if now - self._last < self.min_interval:
            return Gst.FlowReturn.OK           # descarta: limita a taxa de quadros
        self._last = now
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if ok:
            try:
                data = bytes(info.data)
            finally:
                buf.unmap(info)
            caps = sample.get_caps().get_structure(0)
            w = caps.get_value("width") if caps.has_field("width") else 0
            h = caps.get_value("height") if caps.has_field("height") else 0
            GLib.idle_add(self._deliver, data, w, h)
        return Gst.FlowReturn.OK

    def _deliver(self, data, w, h):
        if self.running:
            self._got_sample = True
            self.on_sample(data, w, h)
        return False

    def _bus_error(self, _bus, msg):
        err, _dbg = msg.parse_error()
        warn(f"erro no teste de câmera/microfone (modo {self._index}): {err.message}")
        self._next_or_fail(err.message)


class CameraTest(_Stream):
    """on_frame(bytes BGRx, largura, altura)."""

    def __init__(self, on_frame, on_error):
        super().__init__(VIDEO_PIPES, on_frame, on_error, min_interval=0.9 / VIDEO_FPS)


class MicTest(_Stream):
    """on_level(dBFS)."""

    def __init__(self, on_level, on_error):
        super().__init__(AUDIO_PIPES, lambda data, _w, _h: on_level(level_db(data)), on_error)
