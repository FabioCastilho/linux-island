"""Registro de erros que a ilha engole de propósito (para nunca travar), mas sem sumir com eles.

`warn("o que falhou", exc)` escreve uma linha no stderr e num arquivo de log pequeno
(~/.local/state/linux-island/island.log). A mesma mensagem não se repete mais de uma vez
por minuto, para um erro de timer de 2 s não encher o disco.
"""
import os
import sys
import time

from gi.repository import GLib

LOG_PATH = os.path.join(GLib.get_user_state_dir(), "linux-island", "island.log")
MAX_BYTES = 256 * 1024
REPEAT_S = 60

_last = {}


def _rotate():
    try:
        if os.path.getsize(LOG_PATH) > MAX_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
    except OSError:
        pass


def warn(what, exc=None):
    """Registra `what` (e a exceção, se houver). Nunca levanta erro."""
    text = f"{what}: {type(exc).__name__}: {exc}" if exc is not None else what
    now = time.monotonic()
    if now - _last.get(text, -REPEAT_S) < REPEAT_S:
        return
    _last[text] = now
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [island] {text}"
    print(line, file=sys.stderr, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        _rotate()
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass
