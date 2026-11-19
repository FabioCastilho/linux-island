"""Sessões do Claude Code em andamento: lê ~/.claude/sessions/*.json (estado ao vivo) e,
do histórico da conversa, o título e o último pedido de cada uma."""
import glob
import json
import os
import time

SESS_DIR = os.path.expanduser("~/.claude/sessions")
PROJECTS = os.path.expanduser("~/.claude/projects")
HOME = os.path.expanduser("~")

_text_cache = {}  # sid -> (path, size, title, prompt)


def _alive(pid):
    try:
        os.kill(pid, 0)
        with open(f"/proc/{pid}/comm") as f:
            return "claude" in f.read() or "node" in f.read()
    except (OSError, ValueError):
        return False


def _tail_text(path, size):
    """Último 'last-prompt' e 'ai-title' do histórico (lê só o final do arquivo)."""
    title = prompt = None
    for chunk in (256 * 1024, 4 * 1024 * 1024):
        try:
            with open(path, "rb") as f:
                f.seek(max(0, size - chunk))
                lines = f.read().splitlines()
        except OSError:
            return None, None
        for line in reversed(lines):
            if prompt is None and b'"last-prompt"' in line[:60]:
                try:
                    prompt = json.loads(line).get("lastPrompt")
                except ValueError:
                    pass
            elif title is None and b'"ai-title"' in line[:60]:
                try:
                    title = json.loads(line).get("aiTitle")
                except ValueError:
                    pass
            if prompt and title:
                return title, prompt
        if size <= chunk:
            break
    return title, prompt


def _texts(sid):
    cached = _text_cache.get(sid)
    path = cached[0] if cached else None
    if path is None or not os.path.exists(path):
        found = glob.glob(os.path.join(PROJECTS, "*", f"{sid}.jsonl"))
        path = found[0] if found else None
    if path is None:
        return None, None
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, None
    if cached and cached[0] == path and cached[1] == size:
        return cached[2], cached[3]
    title, prompt = _tail_text(path, size)
    _text_cache[sid] = (path, size, title, prompt)
    return title, prompt


def read_sessions():
    """Sessões vivas, da mais recentemente ativa para a mais antiga."""
    out = []
    for path in glob.glob(os.path.join(SESS_DIR, "*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
            pid, sid = int(d["pid"]), d["sessionId"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not _alive(pid):
            continue
        cwd = d.get("cwd", "")
        project = "~" if cwd.rstrip("/") == HOME else (os.path.basename(cwd.rstrip("/")) or "/")
        title, prompt = _texts(sid)
        out.append({"pid": pid, "sid": sid, "cwd": cwd, "project": project,
                    "name": d.get("name", ""), "status": d.get("status", "?"),
                    "since": (d.get("statusUpdatedAt") or d.get("updatedAt") or 0) / 1000,
                    "title": title, "prompt": prompt})
    out.sort(key=lambda s: s["since"], reverse=True)
    return out


def ago(ts):
    s = max(0, int(time.time() - ts))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s // 3600} h"
    return f"{s // 86400} d"
