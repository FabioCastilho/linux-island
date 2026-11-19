"""Detecta câmera e microfone em uso, como o ponto laranja/verde do macOS.

Microfone e câmera de apps modernos passam pelo PipeWire: um stream de entrada em estado
"running". Apps que abrem /dev/video* direto (sem PipeWire) aparecem numa varredura de /proc.
Capturas do áudio do sistema (monitor) e o "peak detect" do applet de volume não contam.
Roda numa thread, a cada poucos segundos, só enquanto o recurso está ligado.
"""
import json
import os
import subprocess
import threading

from gi.repository import GLib

from logutil import warn

INTERVAL_S = 5
SYSTEM_PROCS = {"pipewire", "wireplumber", "pipewire-pulse", "pipewire-media-session"}


def _name(props):
    return (props.get("application.name") or props.get("application.process.binary")
            or props.get("node.name") or "?")


def parse_pw_dump(text):
    """Saída do `pw-dump` -> {"mic": [apps], "cam": [apps]} com streams realmente ativos."""
    out = {"mic": [], "cam": []}
    try:
        objs = json.loads(text)
    except (ValueError, TypeError):
        return out
    for o in objs if isinstance(objs, list) else []:
        if not isinstance(o, dict) or o.get("type") != "PipeWire:Interface:Node":
            continue
        info = o.get("info") or {}
        props = info.get("props") or {}
        if info.get("state") != "running":
            continue
        cls = props.get("media.class")
        if cls == "Stream/Input/Audio":
            if props.get("stream.capture.sink") in (True, "true"):
                continue                       # captura o áudio do sistema, não o microfone
            if props.get("media.name") == "Peak detect":
                continue                       # medidor de nível do applet de volume
            out["mic"].append(_name(props))
        elif cls == "Stream/Input/Video":
            out["cam"].append(_name(props))
    return out


def scan_video_openers(proc="/proc"):
    """Nomes dos processos (seus) com /dev/video* aberto, sem contar o próprio PipeWire."""
    names = []
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return names
    for pid in pids:
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue                           # processo de outro usuário ou já terminou
        for fd in fds:
            try:
                target = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if target.startswith("/dev/video"):
                try:
                    with open(os.path.join(proc, pid, "comm")) as f:
                        comm = f.read().strip()
                except OSError:
                    comm = "?"
                if comm not in SYSTEM_PROCS:
                    names.append(comm)
                break
    return names


def unique(names):
    return list(dict.fromkeys(names))


def poll(proc="/proc"):
    """Uma leitura completa: {"mic": [...], "cam": [...]}."""
    state = {"mic": [], "cam": []}
    try:
        r = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=4)
        # em repouso não há stream de entrada nenhum: nem vale a pena interpretar 200 KB de JSON
        if r.returncode == 0 and "Stream/Input/" in r.stdout:
            state = parse_pw_dump(r.stdout)
    except (OSError, subprocess.SubprocessError) as e:
        warn("pw-dump indisponível; só a varredura de /proc vale para a câmera", e)
    state["cam"] += scan_video_openers(proc)
    return {k: unique(v) for k, v in state.items()}


class PrivacyWatcher:
    def __init__(self, on_change):
        self.on_change = on_change   # chamado na thread da UI com {"mic": [...], "cam": [...]}
        self.state = {"mic": [], "cam": []}
        self._timer = None
        self._busy = False

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add_seconds(INTERVAL_S, self._tick)
            self._tick()

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None
        self._set({"mic": [], "cam": []})

    def _tick(self):
        if self._busy:
            return True
        self._busy = True

        def work():
            try:
                state = poll()
            except Exception as e:  # nunca derruba a ilha
                warn("detecção de câmera/microfone", e)
                state = None
            GLib.idle_add(self._done, state)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _done(self, state):
        self._busy = False
        if state is not None and self._timer is not None:
            self._set(state)
        return False

    def _set(self, state):
        if state != self.state:
            self.state = state
            self.on_change(state)
