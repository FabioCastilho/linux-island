"""Lê o histórico do Claude Code (~/.claude/projects/*/*.jsonl) e resume o uso de tokens.

Leitura incremental: guarda em cache o ponto onde parou em cada arquivo, então só o que
foi escrito depois é lido de novo. Mensagens vêm repetidas (uma linha por bloco de
conteúdo), então são unidas pelo id da mensagem.
"""
import glob
import json
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

from gi.repository import GLib

from logutil import warn

ROOT = os.path.expanduser("~/.claude/projects")
CACHE = os.path.join(GLib.get_user_state_dir(), "linux-island", "claude_usage.json")
VERSION = 2


def _home_prefix(home=None):
    """O Claude Code nomeia a pasta de cada projeto trocando tudo que não é letra ou número
    do caminho por '-': /home/ana/app vira -home-ana-app. Daqui sai o prefixo da home."""
    return re.sub(r"[^A-Za-z0-9]", "-", home or os.path.expanduser("~"))


def project_name(dirname, home=None):
    prefix = _home_prefix(home)
    name = dirname.removeprefix(prefix + "-").removeprefix(prefix)
    return name.replace("-", "/", 1) if name else "~"


class UsageStore:
    def __init__(self):
        self.lock = threading.Lock()
        self._saved_at = 0.0
        self.files, self.events, self.sessions = {}, {}, {}
        self._load()

    def _load(self):
        try:
            with open(CACHE) as f:
                d = json.load(f)
            if d.get("v") == VERSION:
                self.files, self.events, self.sessions = d["files"], d["events"], d["sessions"]
        except FileNotFoundError:
            pass  # primeira execução: ainda não há cache
        except (OSError, ValueError, KeyError) as e:
            warn("cache de uso do Claude ilegível, recomeçando", e)

    def _save(self):
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"v": VERSION, "files": self.files, "events": self.events,
                           "sessions": self.sessions}, f)
            os.replace(tmp, CACHE)
        except OSError as e:
            warn("não deu para salvar o cache de uso do Claude", e)

    def refresh(self):
        """Lê o que há de novo. Roda em thread; devolve True se algo mudou."""
        changed = False
        with self.lock:
            for path in glob.glob(os.path.join(ROOT, "*", "*.jsonl")):
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                off = self.files.get(path, 0)
                if size == off:
                    continue
                if size < off:
                    off = 0
                project = project_name(os.path.basename(os.path.dirname(path)))
                with open(path, "rb") as fh:
                    fh.seek(off)
                    for line in fh:
                        if not line.endswith(b"\n"):
                            break  # linha ainda sendo escrita: lê na próxima
                        off += len(line)
                        if b'"usage"' in line and b'"type":"assistant"' in line:
                            changed |= self._add_message(line, project)
                        elif b'"cost-state"' in line:
                            changed |= self._add_cost(line)
                self.files[path] = off
            if changed and time.monotonic() - self._saved_at > 60:
                self._save()  # o cache é grande: no máximo uma gravação por minuto
                self._saved_at = time.monotonic()
        return changed

    def _add_message(self, line, project):
        try:
            d = json.loads(line)
            m = d["message"]
            u = m["usage"]
            mid = m["id"]
        except (ValueError, KeyError, TypeError):
            return False
        if m.get("model") == "<synthetic>":
            return False
        tools = [b["name"] for b in m.get("content", []) if isinstance(b, dict)
                 and b.get("type") == "tool_use"]
        try:
            ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            return False
        ev = self.events.get(mid)
        vals = [u.get("input_tokens", 0), u.get("cache_creation_input_tokens", 0),
                u.get("cache_read_input_tokens", 0), u.get("output_tokens", 0)]
        if ev is None:
            self.events[mid] = {"t": ts, "p": project, "m": m.get("model", "?"),
                                "u": vals, "tools": tools,
                                "s": d.get("session_id") or d.get("sessionId", "")}
        else:
            ev["u"] = [max(a, b) for a, b in zip(ev["u"], vals)]
            ev["tools"] = ev["tools"] + [t for t in tools if t not in ev["tools"]]
        return True

    def _add_cost(self, line):
        try:
            d = json.loads(line)
            sid, cost = d["sessionId"], float(d["totalCostUSD"])
        except (ValueError, KeyError, TypeError):
            return False
        self.sessions[sid] = cost
        return True

    # --- resumo -----------------------------------------------------------
    def summary(self, days):
        """days=1: hoje (desde a meia-noite local); 7 / 30: últimos N dias."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        since = (today - timedelta(days=days - 1)).timestamp()
        tot = [0, 0, 0, 0]
        sess_all, sess_in = defaultdict(int), defaultdict(int)
        by = {"tool": defaultdict(int), "project": defaultdict(int), "model": defaultdict(int)}
        count = 0
        with self.lock:
            for ev in self.events.values():
                i, cw, cr, o = ev["u"]
                sess_all[ev["s"]] += i + cw + o
                if ev["t"] < since:
                    continue
                sess_in[ev["s"]] += i + cw + o
                for k in range(4):
                    tot[k] += ev["u"][k]
                work = i + cw + o  # tokens "de trabalho": cache lido fica de fora
                count += 1
                by["project"][ev["p"]] += work
                by["model"][ev["m"]] += work
                tools = ev["tools"] or ["(resposta)"]
                for t in tools:  # a mensagem é dividida igualmente entre as ferramentas
                    by["tool"][t] += work / len(tools)
        # custo: o da sessão (informado pelo Claude Code) na proporção dos tokens do período
        cost = sum(self.sessions.get(sid, 0.0) * part / sess_all[sid]
                   for sid, part in sess_in.items() if sess_all[sid])
        return {"cost": cost, "in": tot[0] + tot[1], "out": tot[3], "cache_read": tot[2],
                "total": tot[0] + tot[1] + tot[3], "messages": count,
                "tool": self._top(by["tool"]), "project": self._top(by["project"]),
                "model": self._top(by["model"])}

    def daily(self, days=7):
        """[(data, tokens de trabalho, custo)] dos últimos `days` dias, do mais antigo ao de hoje.
        O custo usa a mesma regra do summary(): o da sessão, na proporção dos tokens."""
        today = datetime.now().date()
        keys = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
        tokens, cost = defaultdict(int), defaultdict(float)
        with self.lock:
            sess_all = defaultdict(int)
            for ev in self.events.values():
                i, cw, _cr, o = ev["u"]
                sess_all[ev["s"]] += i + cw + o
            for ev in self.events.values():
                day = datetime.fromtimestamp(ev["t"]).date()
                if day < keys[0] or day > today:
                    continue
                i, cw, _cr, o = ev["u"]
                work = i + cw + o
                tokens[day] += work
                if sess_all[ev["s"]]:
                    cost[day] += self.sessions.get(ev["s"], 0.0) * work / sess_all[ev["s"]]
        return [(d, tokens[d], cost[d]) for d in keys]

    @staticmethod
    def _top(d, n=6):
        items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)
        total = sum(v for _k, v in items) or 1
        top = items[:n]
        rest = sum(v for _k, v in items[n:])
        if rest:
            top.append(("outros", rest))
        return [(k, int(v), v / total) for k, v in top]


def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k" if n < 100_000 else f"{n / 1_000:.0f}k"
    return str(n)


def pretty_model(name):
    n = name.removeprefix("claude-")
    parts = n.split("-")
    if len(parts) >= 3 and parts[1].isdigit():
        return f"{parts[0].capitalize()} {parts[1]}.{parts[2]}"
    return n
