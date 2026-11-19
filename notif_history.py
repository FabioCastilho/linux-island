"""Histórico das notificações que a ilha viu. Fica só na memória (some ao reiniciar):
o conteúdo de notificações pode ser privado, então nada disso vai para o disco."""
import time

DUP_WINDOW_S = 2.0  # a mesma notificação em seguida (apps que repetem) conta uma vez só


class Entry:
    def __init__(self, notification, ts):
        self.n = notification
        self.ts = ts
        self.read = False


class NotificationHistory:
    def __init__(self, max_items=50, clock=time.time):
        self.max_items = max_items
        self._clock = clock
        self.items = []          # mais recente primeiro
        self._listeners = []

    def connect(self, fn):
        self._listeners.append(fn)

    def _changed(self):
        for fn in list(self._listeners):
            fn()

    @property
    def unread(self):
        return sum(1 for e in self.items if not e.read)

    def add(self, n):
        now = self._clock()
        if self.items:
            last = self.items[0]
            same = (last.n.app, last.n.summary, last.n.body) == (n.app, n.summary, n.body)
            if same and now - last.ts < DUP_WINDOW_S:
                return False
        self.items.insert(0, Entry(n, now))
        del self.items[self.max_items:]
        self._changed()
        return True

    def set_max(self, max_items):
        self.max_items = max_items
        if len(self.items) > max_items:
            del self.items[max_items:]
            self._changed()

    def mark_read(self):
        if any(not e.read for e in self.items):
            for e in self.items:
                e.read = True
            self._changed()

    def clear(self):
        if self.items:
            self.items.clear()
            self._changed()
