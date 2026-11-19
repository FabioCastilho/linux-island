"""Dados do sistema para a página "Sistema": áudio, rede, bateria e brilho.

As funções `parse_*` e `read_*` são puras (recebem texto ou caminho), para poderem ser
testadas sem GTK nem hardware. Comandos externos rodam numa thread (`run_async`) para a ilha
nunca esperar um processo lento.
"""
import glob
import json
import os
import subprocess
import threading

from gi.repository import Gio, GLib

from logutil import warn

SINK = "@DEFAULT_AUDIO_SINK@"
VIRTUAL_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "vnet", "tun", "tap", "wg",
                    "tailscale", "zt", "vmnet", "podman", "cni", "flannel")


def run_async(cmd, cb=None, timeout=4):
    """Roda `cmd` numa thread; chama cb(stdout) na thread da UI (None se falhou)."""
    def work():
        out = None
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                out = r.stdout
            else:
                warn(f"{cmd[0]} saiu com {r.returncode}: {r.stderr.strip()[:120]}")
        except (OSError, subprocess.SubprocessError) as e:
            warn(f"não deu para rodar {cmd[0]}", e)
        if cb:
            GLib.idle_add(lambda: (cb(out), False)[1])
    threading.Thread(target=work, daemon=True).start()


# --- áudio ------------------------------------------------------------------
def parse_wpctl_volume(text):
    """'Volume: 0.45 [MUTED]' -> (0.45, True). None se não entender."""
    try:
        parts = (text or "").split()
        return float(parts[1]), "[MUTED]" in parts
    except (IndexError, ValueError):
        return None


def parse_pactl_sinks(text):
    """Saída de `pactl -f json list sinks` -> [(nome, descrição)]."""
    try:
        return [(s["name"], s.get("description") or s["name"]) for s in json.loads(text)]
    except (ValueError, KeyError, TypeError):
        return []


class Audio:
    def get(self, cb):
        """cb((volume, mudo)) ou cb(None)."""
        run_async(["wpctl", "get-volume", SINK], lambda out: cb(parse_wpctl_volume(out)))

    def set_volume(self, fraction):
        v = max(0.0, min(1.0, fraction))
        run_async(["wpctl", "set-volume", SINK, f"{v:.2f}"])

    def toggle_mute(self, cb=None):
        run_async(["wpctl", "set-mute", SINK, "toggle"], cb)

    def sinks(self, cb):
        """cb(lista de (nome, descrição), nome do padrão) — o padrão pode ser ''."""
        state = {}

        def got_default(out):
            cb(state.get("list", []), (out or "").strip())

        def got_list(out):
            state["list"] = parse_pactl_sinks(out)
            run_async(["pactl", "get-default-sink"], got_default)

        run_async(["pactl", "-f", "json", "list", "sinks"], got_list)

    def set_default(self, name, cb=None):
        run_async(["pactl", "set-default-sink", name], cb)


# --- rede -------------------------------------------------------------------
def parse_net_dev(text):
    """/proc/net/dev -> {interface: (bytes recebidos, bytes enviados)}."""
    out = {}
    for line in (text or "").splitlines()[2:]:
        name, _sep, rest = line.partition(":")
        fields = rest.split()
        if len(fields) >= 9:
            try:
                out[name.strip()] = (int(fields[0]), int(fields[8]))
            except ValueError:
                continue
    return out


def physical(names):
    return [n for n in names if not n.startswith(VIRTUAL_PREFIXES)]


def read_net_totals(path="/proc/net/dev"):
    """Total (rx, tx) das interfaces físicas, ou None se não deu para ler."""
    try:
        with open(path) as f:
            stats = parse_net_dev(f.read())
    except OSError as e:
        warn("não deu para ler /proc/net/dev", e)
        return None
    keep = physical(stats)
    return sum(stats[n][0] for n in keep), sum(stats[n][1] for n in keep)


class NetRate:
    """Velocidade (bytes/s) entre duas leituras dos contadores."""

    def __init__(self):
        self._last = None

    def update(self, totals, now):
        if totals is None:
            return None
        last, self._last = self._last, (totals, now)
        if last is None or now <= last[1]:
            return (0.0, 0.0)
        dt = now - last[1]
        # contador que voltou atrás (interface reiniciada): conta como zero, não negativo
        return (max(0.0, (totals[0] - last[0][0]) / dt), max(0.0, (totals[1] - last[0][1]) / dt))


def fmt_rate(bps):
    for unit, div in (("GB/s", 1e9), ("MB/s", 1e6), ("KB/s", 1e3)):
        if bps >= div:
            v = bps / div
            return f"{v:.1f} {unit}" if v < 10 else f"{v:.0f} {unit}"
    return f"{int(bps)} B/s"


def _split_nmcli(line):
    """Divide uma linha do modo terse do nmcli (':' separa, '\\:' é um ':' do texto)."""
    parts, cur, esc = [], "", False
    for ch in line:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def parse_nmcli_active(text):
    """`nmcli -t -f TYPE,NAME,DEVICE connection show --active` -> [(tipo, nome, dispositivo)]."""
    rows = []
    for line in (text or "").splitlines():
        p = _split_nmcli(line)
        if len(p) >= 3 and p[0]:
            rows.append((p[0], p[1], p[2]))
    return rows


def describe_connection(rows):
    """Resumo da conexão principal: (ícone, nome, tem VPN). Sem conexão: ('none', '', False)."""
    vpn = any(t in ("vpn", "wireguard") for t, _n, _d in rows)
    main = [r for r in rows if r[0] not in ("vpn", "wireguard", "bridge", "loopback", "tun")
            and not r[2].startswith(VIRTUAL_PREFIXES)]
    if not main:
        return "none", "", vpn
    t, name, _dev = main[0]
    return ("wifi" if "wireless" in t else "ethernet"), name, vpn


def read_connection(cb):
    run_async(["nmcli", "-t", "-f", "TYPE,NAME,DEVICE", "connection", "show", "--active"],
              lambda out: cb(describe_connection(parse_nmcli_active(out)) if out is not None
                             else None))


# --- bateria e brilho (só existem em notebooks) --------------------------------
def _read(path):
    with open(path) as f:
        return f.read().strip()


def read_battery(base="/sys/class/power_supply"):
    """(porcentagem, carregando) da primeira bateria, ou None se o PC não tem."""
    for d in sorted(glob.glob(os.path.join(base, "BAT*"))):
        try:
            pct = int(_read(os.path.join(d, "capacity")))
            status = _read(os.path.join(d, "status"))
            return pct, status in ("Charging", "Full")
        except (OSError, ValueError):
            continue
    return None


def read_backlight(base="/sys/class/backlight"):
    """(nome, atual, máximo) do primeiro backlight, ou None se não houver."""
    for d in sorted(glob.glob(os.path.join(base, "*"))):
        try:
            cur = int(_read(os.path.join(d, "brightness")))
            mx = int(_read(os.path.join(d, "max_brightness")))
            if mx > 0:
                return os.path.basename(d), cur, mx
        except (OSError, ValueError):
            continue
    return None


def set_backlight(name, value):
    """Muda o brilho pelo logind (não precisa de root nem de brightnessctl)."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        bus.call("org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
                 "org.freedesktop.login1.Session", "SetBrightness",
                 GLib.Variant("(ssu)", ("backlight", name, int(value))), None,
                 Gio.DBusCallFlags.NONE, 2000, None, None, None)
    except GLib.Error as e:
        warn("não deu para mudar o brilho", e)
