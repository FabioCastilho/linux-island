"""Tema automático: troca entre um tema claro e um escuro seguindo o KDE ou o horário.

A decisão (`decide`) é uma função pura. A troca acontece só quando o período muda (claro ->
escuro ou o contrário) e quando o modo é ligado ou a ilha abre: se você escolher outro tema
no meio do período, ele fica até a próxima mudança.
"""
from datetime import datetime

from gi.repository import Gio

import kde
import themes
from logutil import warn


def schedule_dark(hour, start, end):
    """Escuro das `start`h às `end`h (pode atravessar a meia-noite). start == end: nunca."""
    if start == end:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


def decide(mode, kde_dark, hour, start, end):
    """'dark', 'light' ou None (sem automação ou sem informação)."""
    if mode == "kde":
        return None if kde_dark is None else ("dark" if kde_dark else "light")
    if mode == "schedule":
        return "dark" if schedule_dark(hour, start, end) else "light"
    return None


class AutoTheme:
    def __init__(self, cfg, on_kde_change=lambda: None, kde_path=kde.PATH):
        self.cfg, self.kde_path = cfg, kde_path
        self.on_kde_change = on_kde_change
        self._last = None        # último período aplicado: 'dark' | 'light'
        self._monitor = None
        self._reload_id = None

    def start(self):
        """Observa o kdeglobals (troca de tema e de cor de destaque no KDE valem na hora)."""
        try:
            self._monitor = Gio.File.new_for_path(self.kde_path).monitor_file(
                Gio.FileMonitorFlags.WATCH_MOVES, None)
            self._monitor.connect("changed", self._changed)
        except Exception as e:   # sem KDE o recurso só não funciona
            warn("não deu para observar o kdeglobals", e)
        self.evaluate(force=True)

    def _changed(self, *_a):
        from gi.repository import GLib
        if self._reload_id:
            GLib.source_remove(self._reload_id)
        # o KDE grava o arquivo em várias etapas: espera assentar
        self._reload_id = GLib.timeout_add(400, self._after_kde_change)

    def _after_kde_change(self):
        self._reload_id = None
        self.on_kde_change()
        self.evaluate()
        return False

    def evaluate(self, force=False, now=None):
        """Aplica o tema do período atual se ele mudou (ou se `force`)."""
        cfg = self.cfg
        mode = cfg["theme_auto"]
        if mode == "off":
            self._last = None
            return None
        hour = (now or datetime.now()).hour
        period = decide(mode, kde.is_dark(self.kde_path), hour,
                        cfg["theme_dark_from_h"], cfg["theme_dark_to_h"])
        if period is None or (period == self._last and not force):
            return None
        self._last = period
        name = cfg["theme_dark"] if period == "dark" else cfg["theme_light"]
        theme = next((t for t in themes.all_themes() if t["name"] == name), None)
        if theme is None:
            warn(f"tema automático: não existe o tema “{name}”")
            return None
        themes.apply(cfg, theme)
        return period
