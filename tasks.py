"""Lista de tarefas rápidas, salva em ~/.local/state/linux-island/tasks.json (só no seu PC)."""
import json
import os
import time

from gi.repository import GLib

from logutil import warn

PATH = os.path.join(GLib.get_user_state_dir(), "linux-island", "tasks.json")
MAX_ITEMS = 100
MAX_TEXT = 200


class Tasks:
    def __init__(self, path=PATH):
        self.path = path
        self.items = []          # [{"id", "text", "done", "ts"}], na ordem em que aparecem
        self._listeners = []
        self._next_id = 1
        self._load()

    def connect(self, fn):
        self._listeners.append(fn)

    def _changed(self):
        self._save()
        for fn in list(self._listeners):
            fn()

    # --- disco ---------------------------------------------------------------
    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            warn("tasks.json ilegível, começando vazio", e)
            return
        if not isinstance(data, list):
            return
        for d in data[:MAX_ITEMS]:
            if isinstance(d, dict) and isinstance(d.get("text"), str) and d["text"].strip():
                self.items.append({"id": self._next_id, "text": d["text"][:MAX_TEXT],
                                   "done": bool(d.get("done")),
                                   "ts": d.get("ts") if isinstance(d.get("ts"), (int, float)) else 0})
                self._next_id += 1

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump([{"text": t["text"], "done": t["done"], "ts": t["ts"]}
                           for t in self.items], f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as e:
            warn("não deu para salvar as tarefas", e)

    # --- operações -----------------------------------------------------------
    @property
    def pending(self):
        return sum(1 for t in self.items if not t["done"])

    def add(self, text):
        text = " ".join((text or "").split())[:MAX_TEXT]
        if not text or len(self.items) >= MAX_ITEMS:
            return False
        self.items.insert(0, {"id": self._next_id, "text": text, "done": False, "ts": time.time()})
        self._next_id += 1
        self._changed()
        return True

    def toggle(self, tid):
        for t in self.items:
            if t["id"] == tid:
                t["done"] = not t["done"]
                self._changed()
                return

    def remove(self, tid):
        n = len(self.items)
        self.items = [t for t in self.items if t["id"] != tid]
        if len(self.items) != n:
            self._changed()

    def clear_done(self):
        if any(t["done"] for t in self.items):
            self.items = [t for t in self.items if not t["done"]]
            self._changed()
