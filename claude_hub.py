"""Página "Claude Code" da ilha expandida: sessões e uso numa página só, mais larga.

À esquerda os agentes (dock + detalhe com o Clawd, pasta e terminal); à direita o gasto e os
tokens. Reaproveita IAPage e ClaudePage, só mais estreitas; cada uma continua cuidando do seu
próprio timer (liga ao aparecer, desliga ao sumir).
"""
from gi.repository import Gtk

from claude_view import ClaudePage
from ia_view import IAPage


class _Agents(IAPage):
    WIDTH = 300


class _Usage(ClaudePage):
    WIDTH = 314

    def __init__(self, cfg=None):
        super().__init__(cfg)
        # em coluna estreita o rodapé não cabe numa linha: quebra em vez de alargar a ilha
        self.foot.set_line_wrap(True)
        self.foot.set_max_width_chars(40)


class ClaudeHub(Gtk.Box):
    def __init__(self, cfg=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.agents = _Agents()
        self.usage = _Usage(cfg)
        self.agents.set_valign(Gtk.Align.START)
        self.usage.set_valign(Gtk.Align.START)
        self.pack_start(self.agents, False, False, 0)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_top(14)
        sep.set_margin_bottom(14)
        self.pack_start(sep, False, False, 0)
        self.pack_start(self.usage, False, False, 0)
