"""Leva o foco para o terminal onde uma sessão do Claude Code está rodando (KDE Plasma 6).

O terminal é um ancestral do processo do `claude`. No Wayland um app não pode pedir foco a
janelas de outros, então a ilha carrega um pequeno script no KWin que ativa a janela cujo PID
é o de um desses ancestrais. Limite: terminais com abas (Konsole) têm um PID só, então vai-se à
janela, não à aba; e dentro de tmux/screen o ancestral é o servidor, sem janela.
"""
import json
import os
import subprocess
import threading
import time

from gi.repository import GLib

from logutil import warn

SCRIPT_NAME = "linux-island-focus"
SCRIPT_PATH = os.path.join(GLib.get_user_state_dir(), "linux-island", "focus_window.js")
SKIP = {"systemd", "init", "(sd-pam)"}  # ancestrais que nunca têm janela


def parse_stat(text):
    """Conteúdo de /proc/<pid>/stat -> (comm, ppid). O nome fica entre parênteses e pode
    ter espaços e parênteses; por isso corta no último ')'."""
    try:
        head, _sep, tail = text.rpartition(")")
        comm = head.partition("(")[2]
        return comm, int(tail.split()[1])
    except (IndexError, ValueError):
        return None


def ancestors(pid, proc="/proc", limit=40):
    """[(pid, comm)] do pai de `pid` para cima, até a raiz (o próprio `pid` não entra)."""
    out = []
    cur = pid
    for _i in range(limit):
        try:
            with open(os.path.join(proc, str(cur), "stat")) as f:
                parsed = parse_stat(f.read())
        except OSError:
            break
        if parsed is None or parsed[1] <= 1:
            break
        cur = parsed[1]
        try:
            with open(os.path.join(proc, str(cur), "stat")) as f:
                comm = (parse_stat(f.read()) or ("?", 0))[0]
        except OSError:
            break
        out.append((cur, comm))
    return out


def candidate_pids(pid, proc="/proc"):
    """PIDs que podem ser donos da janela, do mais próximo ao mais distante."""
    return [p for p, comm in ancestors(pid, proc) if comm not in SKIP]


def build_script(pids):
    """JS do KWin que ativa a janela do primeiro PID da lista que tiver uma. Só inteiros
    entram no texto, vindos do /proc: nada do que a sessão escreve chega ao script."""
    safe = json.dumps([int(p) for p in pids])
    return (
        f"var pids = {safe};\n"
        "var wins = workspace.windowList();\n"
        "outer: for (var i = 0; i < pids.length; i++) {\n"
        "  for (var j = 0; j < wins.length; j++) {\n"
        "    if (wins[j].pid === pids[i]) {\n"
        "      wins[j].minimized = false;\n"
        "      workspace.activeWindow = wins[j];\n"
        "      break outer;\n"
        "    }\n"
        "  }\n"
        "}\n")


def _qdbus(*args):
    return subprocess.run(["qdbus6", "org.kde.KWin", *args], capture_output=True, text=True,
                          timeout=4)


def _run_script(js):
    try:
        os.makedirs(os.path.dirname(SCRIPT_PATH), exist_ok=True)
        with open(SCRIPT_PATH, "w") as f:
            f.write(js)
        _qdbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", SCRIPT_NAME)
        r = _qdbus("/Scripting", "org.kde.kwin.Scripting.loadScript", SCRIPT_PATH, SCRIPT_NAME)
        sid = r.stdout.strip()
        if r.returncode != 0 or not sid.lstrip("-").isdigit() or int(sid) < 0:
            warn(f"KWin não carregou o script de foco: {r.stderr.strip()[:100] or sid}")
            return
        _qdbus(f"/Scripting/Script{sid}", "org.kde.kwin.Script.run")
        time.sleep(0.4)  # dá tempo de rodar antes de descarregar
        _qdbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", SCRIPT_NAME)
    except (OSError, subprocess.SubprocessError) as e:
        warn("não deu para focar o terminal", e)


def focus_session(pid):
    """Pede ao KWin o foco do terminal da sessão. False se não há candidato (sem janela
    possível); True se o pedido foi enviado — o KWin decide se achou a janela."""
    pids = candidate_pids(pid)
    if not pids:
        return False
    threading.Thread(target=_run_script, args=(build_script(pids),), daemon=True).start()
    return True
