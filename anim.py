"""Velocidade das animações da ilha: um ajuste só para todas as transições.

Cada Revealer/Stack se registra aqui com a duração-base (`register`); trocar a velocidade na
configuração (`set_speed`) reajusta todos na hora, sem reiniciar.
"""
import weakref

SPEEDS = {"none": 0.0, "fast": 0.6, "normal": 1.0, "relaxed": 1.6}
_factor = 1.0
_items = []  # (referência fraca ao widget, duração-base em ms)


def factor():
    return _factor


def ms(base):
    """Duração em ms já ajustada à velocidade escolhida (0 = sem animação)."""
    return int(round(base * _factor))


def register(widget, base_ms):
    """Aplica a duração ajustada ao widget (Revealer ou Stack) e o acompanha nas mudanças."""
    widget.set_transition_duration(ms(base_ms))
    _items.append((weakref.ref(widget), base_ms))
    return widget


def set_speed(name):
    global _factor
    _factor = SPEEDS.get(name, 1.0)
    alive = []
    for ref, base in _items:
        w = ref()
        if w is not None:
            w.set_transition_duration(ms(base))
            alive.append((ref, base))
    _items[:] = alive


def easing_css():
    """Curva do border-radius ao expandir: mais lenta ganha um pouco de balanço."""
    return "cubic-bezier(0.2, 0.9, 0.3, 1.15)" if _factor >= 1.0 else "ease-out"
