"""Cores de alerta e de identidade das páginas (água, reunião, foco, Claude), vindas do tema.

As telas desenhadas com cairo leem daqui na hora de pintar (`palette.WATER` etc.); o CSS recebe
as mesmas cores por config.build_css. `apply(cfg)` atualiza os valores quando o tema muda.
"""
from gi.repository import Gdk

DEFAULTS = {"water": "rgb(41,158,245)", "meeting": "rgb(167,139,250)",
            "focus": "rgb(237,102,82)", "claude": "rgb(217,119,87)"}

WATER = (0.16, 0.62, 0.96)
MEETING = (0.65, 0.55, 0.98)
FOCUS = (0.93, 0.40, 0.32)
CLAUDE = (0.85, 0.47, 0.34)


def parse(spec, fallback):
    c = Gdk.RGBA()
    return (c.red, c.green, c.blue) if c.parse(spec) else fallback


def apply(cfg):
    global WATER, MEETING, FOCUS, CLAUDE
    WATER = parse(cfg["color_water"], WATER)
    MEETING = parse(cfg["color_meeting"], MEETING)
    FOCUS = parse(cfg["color_focus"], FOCUS)
    CLAUDE = parse(cfg["color_claude"], CLAUDE)
