"""Página "Sistema" da ilha expandida: uso da CPU/RAM/temperatura e botões de energia."""
import glob
import math
import os
import subprocess
import time

from gi.repository import Gio, GLib, Gtk

import sysinfo
from i18n import _
from icons import Glyph, glyph_button
from logutil import warn
from views import clip, label
from widgets import Progress, Tweened, load_color

POWER = (  # id, ícone, rótulo, comando
    ("lock", "system-lock-screen-symbolic", "Bloquear", ["loginctl", "lock-session"]),
    ("suspend", "media-playback-pause-symbolic", "Suspender", ["systemctl", "suspend"]),
    ("logout", "system-log-out-symbolic", "Encerrar sessão", ["loginctl", "terminate-session",
                                                    os.environ.get("XDG_SESSION_ID", "self")]),
    ("reboot", "system-reboot-symbolic", "Reiniciar", ["systemctl", "reboot"]),
    ("poweroff", "system-shutdown-symbolic", "Desligar", ["systemctl", "poweroff"]),
)
CONFIRM = {"logout", "reboot", "poweroff"}  # pedem um segundo clique


class KeepAwake:
    """Impede suspensão e tela apagando por inatividade enquanto ativo.

    Usa o inibidor do logind (fecha o fd = libera, até se a ilha cair) e o do
    PowerDevil do KDE, que é quem decide a suspensão por inatividade no Plasma.
    """

    def __init__(self):
        self.fd = None
        self.cookie = None
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sysbus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    @property
    def active(self):
        return self.fd is not None or self.cookie is not None

    def enable(self):
        if self.active:
            return True
        try:
            res, fds = self.sysbus.call_with_unix_fd_list_sync(
                "org.freedesktop.login1", "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager", "Inhibit",
                GLib.Variant("(ssss)", ("idle:sleep", "linux-island",
                                        "Manter o PC acordado", "block")),
                GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None)
            self.fd = fds.steal_fds()[res.get_child_value(0).get_handle()]
        except GLib.Error:
            self.fd = None
        try:
            r = self.bus.call_sync(
                "org.freedesktop.PowerManagement.Inhibit",
                "/org/freedesktop/PowerManagement/Inhibit",
                "org.freedesktop.PowerManagement.Inhibit", "Inhibit",
                GLib.Variant("(ss)", ("linux-island", "Manter o PC acordado")),
                GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, -1, None)
            self.cookie = r.unpack()[0]
        except GLib.Error:
            self.cookie = None
        return self.active

    def disable(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        if self.cookie is not None:
            try:
                self.bus.call_sync(
                    "org.freedesktop.PowerManagement.Inhibit",
                    "/org/freedesktop/PowerManagement/Inhibit",
                    "org.freedesktop.PowerManagement.Inhibit", "UnInhibit",
                    GLib.Variant("(u)", (self.cookie,)), None,
                    Gio.DBusCallFlags.NONE, -1, None)
            except GLib.Error:
                pass
            self.cookie = None


class CpuSampler:
    def __init__(self):
        self._last = self._read()

    @staticmethod
    def _read():
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:]]
        return sum(v), v[3] + v[4]  # total, idle+iowait

    def usage(self):
        total, idle = self._read()
        dt, di = total - self._last[0], idle - self._last[1]
        self._last = (total, idle)
        return 0.0 if dt <= 0 else max(0.0, min(1.0, 1 - di / dt))


def mem_usage():
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":")
            info[k] = int(v.split()[0])
            if "MemAvailable" in info and "MemTotal" in info:
                break
    total, avail = info["MemTotal"], info["MemAvailable"]
    return (total - avail) / total, (total - avail) / 1048576, total / 1048576


def cpu_temp():
    best = None
    for zone in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            name = open(os.path.join(zone, "name")).read().strip()
            if name in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
                return int(open(os.path.join(zone, "temp1_input")).read()) / 1000
        except (OSError, ValueError):
            continue
    for t in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            best = int(open(t).read()) / 1000
            break
        except (OSError, ValueError):
            continue
    return best


class History(Gtk.DrawingArea):
    """Gráfico de linha dos últimos segundos de uso da CPU."""

    N = 40

    def __init__(self):
        super().__init__()
        self.values = [0.0] * self.N
        self.fg = (1, 1, 1)
        self.set_size_request(-1, 54)
        self.set_hexpand(True)
        self.connect("draw", self._draw)

    def push(self, v):
        self.values = self.values[1:] + [v]
        self.queue_draw()

    def _draw(self, _w, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        cr.set_source_rgba(*self.fg, 0.08)
        cr.rectangle(0, h - 1, w, 1)
        cr.fill()
        step = w / (self.N - 1)
        pts = [(i * step, h - 2 - v * (h - 6)) for i, v in enumerate(self.values)]
        cr.move_to(0, h)
        for x, y in pts:
            cr.line_to(x, y)
        cr.line_to(w, h)
        cr.close_path()
        color = load_color(self.values[-1])
        cr.set_source_rgba(*color, 0.22)
        cr.fill()
        cr.move_to(*pts[0])
        for x, y in pts[1:]:
            cr.line_to(x, y)
        cr.set_source_rgb(*color)
        cr.set_line_width(1.8)
        cr.stroke()


class Ring(Tweened, Gtk.DrawingArea):
    def __init__(self, size=96, width=9):
        super().__init__()
        self._tween_init()
        self.size, self.width, self.fg = size, width, (1, 1, 1)
        self.set_size_request(size, size)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        c = self.size / 2
        r = c - self.width / 2 - 1
        cr.set_line_width(self.width)
        cr.set_source_rgba(*self.fg, 0.12)
        cr.arc(c, c, r, 0, 2 * math.pi)
        cr.stroke()
        if self.fraction > 0.005:
            cr.set_line_cap(1)
            cr.set_source_rgb(*load_color(self.fraction))
            cr.arc(c, c, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * self.fraction)
            cr.stroke()


class SystemPage(Gtk.Box):
    WIDTH = 560  # duas colunas: métricas à esquerda, controles à direita

    def __init__(self, cfg, on_awake=lambda on: None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.cfg, self.on_awake = cfg, on_awake
        self.sampler = CpuSampler()
        self.keep_awake = KeepAwake()
        self._timer = None
        self._armed = None
        self._armed_timer = None
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        title = label("title")
        title.set_text(_("Sistema"))
        self.pack_start(title, False, False, 0)

        body = Gtk.Box(spacing=16)
        overlay = Gtk.Overlay()
        self.ring = Ring()
        overlay.add(self.ring)
        self.cpu_lbl = label("big-temp", 0.5)
        self.cpu_lbl.set_halign(Gtk.Align.CENTER)
        self.cpu_lbl.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.cpu_lbl)
        body.pack_start(overlay, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_valign(Gtk.Align.CENTER)
        self.hist = History()
        right.pack_start(self.hist, False, False, 0)
        self.info = label("dim small")
        self.info.set_line_wrap(True)       # coluna estreita: quebra em vez de alargar a ilha
        self.info.set_max_width_chars(22)
        right.pack_start(self.info, False, False, 0)
        body.pack_start(right, True, True, 0)
        net_col, controls = self._build_extras()
        cols = Gtk.Box(spacing=18, homogeneous=True)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left.pack_start(body, False, False, 0)
        left.pack_start(net_col, False, False, 0)
        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        right_col.pack_start(controls, False, False, 0)
        cols.pack_start(left, True, True, 0)
        cols.pack_start(right_col, True, True, 0)
        self.pack_start(cols, False, False, 0)

        awake = Gtk.Box(spacing=8)
        awake_lbl = label("small")
        awake_lbl.set_text(_("Não deixar o PC suspender"))
        awake.pack_start(awake_lbl, True, True, 0)
        self.awake_sw = Gtk.Switch()
        self.awake_sw.set_can_focus(False)
        self.awake_sw.set_valign(Gtk.Align.CENTER)
        self.awake_sw.connect("state-set", self._on_awake)
        awake.pack_end(self.awake_sw, False, False, 0)
        right_col.pack_start(awake, False, False, 0)

        row = Gtk.Box(spacing=6, homogeneous=True)
        self.buttons = {}
        for pid, icon_name, text, cmd in POWER:
            b = Gtk.Button()
            b.set_can_focus(False)
            b.get_style_context().add_class("power-btn")
            if pid == "poweroff":
                b.get_style_context().add_class("danger")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.pack_start(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR),
                           False, False, 0)
            lb = label("power-lbl", 0.5)
            lb.set_text(_(text))
            box.pack_start(lb, False, False, 0)
            b.add(box)
            b.connect("clicked", lambda _b, p=pid, c=cmd, l=lb, t=text: self._press(p, c, l, t))
            row.pack_start(b, True, True, 0)
            self.buttons[pid] = (b, lb, text)
        self.pack_start(row, False, False, 0)

        # só amostra enquanto a página está visível
        self.connect("map", self._start)
        self.connect("unmap", self._stop)

    # --- som, rede, bateria e brilho ---------------------------------------
    def _build_extras(self):
        """Linhas de som, saída de áudio, brilho, rede e bateria. Brilho e bateria só
        aparecem se o PC tiver (notebook); o resto some sozinho se a leitura falhar."""
        self.audio = sysinfo.Audio()
        self._vol_pending = self._vol_timer = None
        self._bright_pending = self._bright_timer = None
        self._sink_names, self._sink_default = [], ""
        self._net = sysinfo.NetRate()
        self._n = 0
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)  # controles (coluna direita)

        # som
        vol = Gtk.Box(spacing=8)
        self.mute_btn, self.vol_glyph = glyph_button("speaker", 16, self._toggle_mute,
                                                     _("Silenciar"))
        self.vol_bar = Progress(self._on_vol_seek, height=14, live=True)
        self.vol_pct = label("time")
        self.vol_pct.set_width_chars(5)
        vol.pack_start(self.mute_btn, False, False, 0)
        vol.pack_start(self.vol_bar, True, True, 0)
        vol.pack_start(self.vol_pct, False, False, 0)
        out = Gtk.Box(spacing=8)
        out.set_margin_start(36)
        self.out_label = label("dim small", 0.0, True)
        self.out_btn = Gtk.Button(label=_("Trocar saída"))
        self.out_btn.set_can_focus(False)
        self.out_btn.get_style_context().add_class("chip")
        self.out_btn.connect("clicked", lambda *_a: self._next_sink())
        out.pack_start(self.out_label, True, True, 0)
        out.pack_end(self.out_btn, False, False, 0)
        self.sound_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.sound_box.pack_start(vol, False, False, 0)
        self.sound_box.pack_start(out, False, False, 0)
        box.pack_start(self.sound_box, False, False, 0)

        # brilho (notebook)
        self.bright_box = Gtk.Box(spacing=8)
        sun = Glyph("sun", 16)
        sun.set_margin_start(6)
        sun.set_margin_end(6)
        self.bright_bar = Progress(self._on_bright_seek, height=14, live=True)
        self.bright_pct = label("time")
        self.bright_pct.set_width_chars(5)
        self.bright_box.pack_start(sun, False, False, 0)
        self.bright_box.pack_start(self.bright_bar, True, True, 0)
        self.bright_box.pack_start(self.bright_pct, False, False, 0)
        box.pack_start(self.bright_box, False, False, 0)

        # rede
        self.net_box = Gtk.Box(spacing=8)
        self.net_glyph = Glyph("ethernet", 16)
        self.net_glyph.set_margin_start(6)
        self.net_glyph.set_margin_end(6)
        self.net_name = label("small", 0.0, True)
        self.vpn_badge = label("badge")
        self.vpn_badge.set_text("VPN")
        self.vpn_badge.set_no_show_all(True)
        self.net_rate = label("time", 1.0)
        self.net_box.pack_start(self.net_glyph, False, False, 0)
        self.net_box.pack_start(self.net_name, True, True, 0)
        self.net_box.pack_start(self.vpn_badge, False, False, 0)
        self.net_box.pack_end(self.net_rate, False, False, 0)

        # bateria (notebook)
        self.bat_box = Gtk.Box(spacing=8)
        bat = Glyph("battery", 16)
        bat.set_margin_start(6)
        bat.set_margin_end(6)
        self.bat_label = label("small", 0.0)
        self.bat_box.pack_start(bat, False, False, 0)
        self.bat_box.pack_start(self.bat_label, True, True, 0)
        box.pack_start(self.bat_box, False, False, 0)
        box.show_all()
        self.net_box.show_all()
        # começam escondidos e só aparecem quando a leitura confirma que existem. Os filhos
        # são mostrados antes: show_all() não entra em widgets com no_show_all.
        for w in (self.sound_box, self.bright_box, self.bat_box):
            w.set_no_show_all(True)
            w.hide()
        return self.net_box, box

    def set_fg(self, fg):
        self.ring.fg = self.hist.fg = fg
        for bar in (self.vol_bar, self.bright_bar):
            bar.fg = fg
            bar.queue_draw()
        self.ring.queue_draw()

    def set_accent(self, accent):
        for bar in (self.vol_bar, self.bright_bar):
            bar.accent = accent
            bar.queue_draw()

    def _toggle_mute(self):
        self.audio.toggle_mute(lambda _out: self._refresh_audio())

    def _on_vol_seek(self, f):
        """Arrastar manda no máximo um comando a cada 80 ms (cada um é um processo)."""
        self._vol_pending = f
        self.vol_pct.set_text(f"{round(f * 100)}%")
        if self._vol_timer is None:
            self._vol_timer = GLib.timeout_add(80, self._flush_vol)

    def _flush_vol(self):
        self._vol_timer = None
        if self._vol_pending is not None:
            self.audio.set_volume(self._vol_pending)
            self._vol_pending = None
        return False

    def _on_bright_seek(self, f):
        self._bright_pending = max(0.05, f)  # nunca apaga a tela de vez
        self.bright_pct.set_text(f"{round(f * 100)}%")
        if self._bright_timer is None:
            self._bright_timer = GLib.timeout_add(80, self._flush_bright)

    def _flush_bright(self):
        self._bright_timer = None
        info = sysinfo.read_backlight()
        if info and self._bright_pending is not None:
            sysinfo.set_backlight(info[0], round(self._bright_pending * info[2]))
        self._bright_pending = None
        return False

    def _refresh_audio(self):
        self.audio.get(self._got_audio)

    def _got_audio(self, res):
        self.sound_box.set_visible(res is not None)
        if res is None:
            return
        v, muted = res
        self.vol_bar.set_fraction(0.0 if muted else min(v, 1.0))
        self.vol_pct.set_text(_("mudo") if muted else f"{round(v * 100)}%")
        self.vol_glyph.set_glyph("muted" if muted or v <= 0.001 else "speaker")

    def _refresh_sinks(self):
        self.audio.sinks(self._got_sinks)

    def _got_sinks(self, sinks, default):
        self._sink_names = [n for n, _d in sinks]
        self._sink_default = default
        desc = dict(sinks).get(default, default)
        self.out_label.set_text(clip(_("Saída: {name}").format(name=desc), 36) if desc else "")
        self.out_btn.set_visible(len(sinks) > 1)

    def _next_sink(self):
        names = self._sink_names
        if len(names) < 2:
            return
        i = names.index(self._sink_default) if self._sink_default in names else -1
        self.audio.set_default(names[(i + 1) % len(names)], lambda _o: self._refresh_sinks())

    def _got_connection(self, res):
        self.net_box.set_visible(res is not None)
        if res is None:
            return
        glyph, name, vpn = res
        self.net_glyph.set_glyph("ethernet" if glyph == "none" else glyph)
        self.net_name.set_text(clip(name, 22) if name else _("Sem conexão"))
        self.vpn_badge.set_visible(vpn)

    def _tick_extras(self):
        n = self._n = self._n + 1
        rate = self._net.update(sysinfo.read_net_totals(), time.monotonic())
        if rate is not None:
            self.net_rate.set_text(f"↓ {sysinfo.fmt_rate(rate[0])}  ↑ {sysinfo.fmt_rate(rate[1])}")
        if n % 2 == 1:
            self._refresh_audio()
        if n % 5 == 1:
            sysinfo.read_connection(self._got_connection)
        if n % 10 == 1:
            self._refresh_sinks()
        if n % 5 == 1:
            bat = sysinfo.read_battery()
            self.bat_box.set_visible(bat is not None)
            if bat:
                state = _("carregando") if bat[1] else _("na bateria")
                self.bat_label.set_text(f"{bat[0]}% · {state}")
            bl = sysinfo.read_backlight()
            self.bright_box.set_visible(bl is not None)
            if bl:
                self.bright_bar.set_fraction(bl[1] / bl[2])
                self.bright_pct.set_text(f"{round(100 * bl[1] / bl[2])}%")

    def _start(self, *_a):
        if self._timer is None:
            self.sampler.usage()
            self._n = 0
            self._timer = GLib.timeout_add(1000, self._tick)
            self._tick()

    def _stop(self, *_a):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self._disarm()

    def _tick(self):
        try:
            self._tick_extras()
        except Exception as e:  # um sensor com defeito não pode derrubar o gráfico de CPU
            warn("página Sistema: leitura extra falhou", e)
        u = self.sampler.usage()
        self.ring.set_fraction(u)
        self.cpu_lbl.set_text(f"{round(u * 100)}%")
        self.hist.push(u)
        try:
            _f, used, total = mem_usage()
            parts = [_("CPU {p}%").format(p=round(u * 100)),
                     _("RAM {u:.1f}/{t:.0f} GB").format(u=used, t=total)]
        except (OSError, KeyError, ValueError):
            parts = [_("CPU {p}%").format(p=round(u * 100))]
        t = cpu_temp()
        if t is not None:
            parts.append(f"{t:.0f}°C")
        self.info.set_text("  ·  ".join(parts))
        return True

    # --- energia ---------------------------------------------------------
    def sync_awake(self):
        """Põe o interruptor, o inibidor e a pílula de acordo com o config (keep_awake)."""
        want = bool(self.cfg["keep_awake"])
        if self.awake_sw.get_active() != want:
            self.awake_sw.set_active(want)  # dispara _on_awake
        else:
            self._on_awake(self.awake_sw, want)

    def _on_awake(self, _sw, state):
        ok = self.keep_awake.enable() if state else (self.keep_awake.disable() or True)
        if state and not ok:
            GLib.idle_add(self.awake_sw.set_active, False)
            self.cfg.set("keep_awake", False)
            self.on_awake(False)
            return False
        self.cfg.set("keep_awake", state)
        self.on_awake(state)
        return False

    def _disarm(self):
        if self._armed_timer:
            GLib.source_remove(self._armed_timer)
            self._armed_timer = None
        if self._armed:
            b, lb, text = self.buttons[self._armed]
            lb.set_text(_(text))
            b.get_style_context().remove_class("armed")
        self._armed = None

    def _press(self, pid, cmd, lb, text):
        if pid in CONFIRM and self._armed != pid:
            self._disarm()
            self._armed = pid
            lb.set_text(_("Confirmar?"))
            self.buttons[pid][0].get_style_context().add_class("armed")
            self._armed_timer = GLib.timeout_add_seconds(3, self._timeout)
            return
        self._disarm()
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def _timeout(self):
        self._armed_timer = None
        self._disarm()
        return False
