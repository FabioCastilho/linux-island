"""Modo "esconder no topo": a ilha sobe para fora da tela e desce quando acontece algo.

Escondida, só uma faixa de SLIVER px fica visível na borda; passar o mouse nela, uma
notificação, um alerta, uma faixa nova ou um clique fazem a ilha descer. Ela sobe de
novo depois de `auto_hide_delay_s` segundos sem nada acontecendo.

Mixin da janela Island; usa self.cfg, self.expanded, self.hovered, self._timers,
self.agenda e self.water dela.
"""
import time

from gi.repository import GLib

import gi
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import GtkLayerShell  # noqa: E402

SLIVER = 3       # px que continuam visíveis (e que o mouse alcança) quando escondida
ANIM_MS = 380


def _ease(t):
    return 1 - (1 - t) ** 3


class AutoHideMixin:
    def _autohide_init(self):
        self._hidden = False
        self._slide_id = None
        self._idle_since = time.monotonic()
        self._margin_now = float(self.cfg["margin_top"])  # ajustado pelo _apply
        GLib.timeout_add(400, self._autohide_tick)

    def _busy(self):
        return (self.expanded or self.hovered or "notif_peek" in self._timers
                or "track_peek" in self._timers or bool(self.agenda.alert)
                or self.water.alerting)

    def _autohide_tick(self):
        if not self.cfg["auto_hide"]:
            if self._hidden:
                self._slide(self._top_margin())
                self._hidden = False
            return True
        if self._busy():
            self.autohide_poke()
        elif (not self._hidden
              and time.monotonic() - self._idle_since > self.cfg["auto_hide_delay_s"]):
            self._hidden = True
            self._slide(-(self.get_allocated_height() - SLIVER))
        return True

    def autohide_poke(self):
        """Algo aconteceu: mostra a ilha e reinicia a contagem para esconder."""
        self._idle_since = time.monotonic()
        if self._hidden:
            self._hidden = False
            self._slide(self._top_margin())

    def _slide(self, target, ms=ANIM_MS):
        """Anima a margem do topo (a ilha sobe/desce) até `target`."""
        if self._slide_id is not None:
            self.remove_tick_callback(self._slide_id)
        start, t0 = self._margin_now, GLib.get_monotonic_time()

        def step(_w, _clock):
            t = min(1.0, (GLib.get_monotonic_time() - t0) / (ms * 1000))
            self._margin_now = start + (target - start) * _ease(t)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, round(self._margin_now))
            if t >= 1.0:
                self._slide_id = None
                return False
            return True

        self._slide_id = self.add_tick_callback(step)
