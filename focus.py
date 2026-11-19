"""Foco / Pomodoro e timer: a lógica do relógio, sem GTK.

Fases: foco, pausa curta, pausa longa e um timer livre. O tempo vem de um relógio injetável
(`clock`), então os testes não precisam esperar minutos de verdade.
"""
import time

PHASES = ("focus", "short", "long", "timer")
TIMER_STEP_MIN = 5
TIMER_DEFAULT_MIN = 10


class Focus:
    def __init__(self, cfg, on_change=lambda: None, on_done=lambda finished, nxt: None,
                 clock=time.monotonic):
        self.cfg = cfg
        self.on_change, self.on_done, self._clock = on_change, on_done, clock
        self.phase = "focus"
        self.running = False
        self.timer_min = TIMER_DEFAULT_MIN
        self.done_focus = 0          # focos completos nesta execução
        self._end = 0.0              # instante (clock) em que acaba, se rodando
        self._left = self.total      # segundos que faltam, se parado

    # --- leitura -------------------------------------------------------------
    @property
    def total(self):
        """Duração da fase atual em segundos."""
        minutes = {"focus": self.cfg["pomo_focus_min"], "short": self.cfg["pomo_short_min"],
                   "long": self.cfg["pomo_long_min"], "timer": self.timer_min}[self.phase]
        return minutes * 60

    @property
    def remaining(self):
        if self.running:
            return max(0.0, self._end - self._clock())
        return self._left

    @property
    def fraction(self):
        """Quanto falta (1 = cheio, 0 = acabou)."""
        return max(0.0, min(1.0, self.remaining / self.total)) if self.total else 0.0

    @property
    def active(self):
        """Rodando ou pausado no meio de uma fase (a pílula mostra o contador)."""
        return self.running or self._left < self.total

    @property
    def round_in_cycle(self):
        """Quantos focos do ciclo atual já foram feitos (0..rounds-1)."""
        return self.done_focus % self.cfg["pomo_rounds"]

    # --- ações ---------------------------------------------------------------
    def start(self):
        if self.running:
            return
        if self._left <= 0:
            self._left = self.total
        self._end = self._clock() + self._left
        self.running = True
        self.on_change()

    def pause(self):
        if not self.running:
            return
        self._left = self.remaining
        self.running = False
        self.on_change()

    def toggle(self):
        self.pause() if self.running else self.start()

    def reset(self):
        self.running = False
        self._left = self.total
        self.on_change()

    def set_phase(self, phase, start=False):
        if phase not in PHASES:
            return
        self.phase = phase
        self.running = False
        self._left = self.total
        if start:
            self.start()
        else:
            self.on_change()

    def skip(self):
        """Pula para a próxima fase sem contar o foco como feito."""
        self.set_phase(self._next_phase(counted=False))

    def adjust_timer(self, delta_min):
        """Só no modo timer e parado: mexe nos minutos."""
        if self.phase != "timer" or self.running:
            return
        self.timer_min = max(1, min(180, self.timer_min + delta_min))
        self._left = self.total
        self.on_change()

    def config_changed(self):
        """Mudou a duração nas configurações: vale se a fase não começou."""
        if not self.active:
            self._left = self.total
            self.on_change()

    def _next_phase(self, counted):
        """`counted`: o foco que acabou já foi somado em done_focus (terminou de verdade).
        Pular um foco no meio nunca leva à pausa longa."""
        if self.phase == "focus":
            if counted and self.done_focus % self.cfg["pomo_rounds"] == 0:
                return "long"
            return "short"
        if self.phase in ("short", "long"):
            return "focus"
        return "timer"

    def tick(self):
        """Chamar cerca de uma vez por segundo. Devolve True se a fase acabou agora."""
        if not self.running:
            return False
        if self.remaining > 0:
            self.on_change()
            return False
        finished = self.phase
        if finished == "focus":
            self.done_focus += 1
        nxt = self._next_phase(counted=True)  # done_focus já foi somado acima
        self.running = False
        self.phase = nxt
        self._left = self.total
        self.on_done(finished, nxt)
        if self.cfg["pomo_auto_next"] and finished != "timer":
            self.start()
        else:
            self.on_change()
        return True


def fmt(seconds):
    s = int(seconds + 0.999) if seconds > 0 else 0  # arredonda para cima: 0:00 só ao acabar
    return f"{s // 60}:{s % 60:02d}"
