"""Reconhece de onde vem o que está tocando (YouTube, WhatsApp...) e desenha a logo.

Navegadores mandam capas aleatórias (a miniatura do vídeo, nada, uma imagem qualquer) e dois
players do mesmo navegador podem informar coisas diferentes. Quando a origem é um serviço
conhecido, a capa vira a logo do serviço: sempre a mesma, venha de onde vier.
Álbuns de verdade (Spotify, players locais) não passam por aqui e continuam com a própria capa.
Serviços de MÚSICA (MUSIC) também: a capa do álbum vale mais que a logo, que só entra quando o
player não manda capa nenhuma.
"""
import math
from urllib.parse import urlparse

# (trecho do host, marca). O mais específico primeiro (music.youtube.com antes de youtube.com).
HOSTS = (
    ("music.youtube.com", "youtube_music"),
    ("youtube.com", "youtube"),
    ("youtu.be", "youtube"),
    ("deezer.com", "deezer"),
    ("music.apple.com", "apple_music"),
    ("web.whatsapp.com", "whatsapp"),
    ("whatsapp.com", "whatsapp"),
    ("twitch.tv", "twitch"),
    ("netflix.com", "netflix"),
    ("web.telegram.org", "telegram"),
)
# O título da aba termina com o nome do site; vale quando o player não informa a URL.
TITLE_SUFFIXES = (
    (" - youtube music", "youtube_music"),
    (" - youtube", "youtube"),
    (" - deezer", "deezer"),
    (" | deezer", "deezer"),
    (" - whatsapp", "whatsapp"),
    (" - twitch", "twitch"),
    (" - netflix", "netflix"),
)
TITLE_EXACT = {"whatsapp": "whatsapp", "netflix": "netflix", "youtube": "youtube"}

# serviços de música: a capa do álbum tem prioridade; a logo é só o plano B
MUSIC = frozenset({"youtube_music", "deezer", "apple_music"})

# cor de destaque de cada marca (r, g, b) para o brilho em volta da capa
COLORS = {
    "youtube": (1.0, 0.0, 0.0), "youtube_music": (1.0, 0.0, 0.0),
    "whatsapp": (0.145, 0.827, 0.40), "twitch": (0.568, 0.275, 1.0),
    "netflix": (0.898, 0.035, 0.078), "telegram": (0.16, 0.65, 0.89),
    "deezer": (0.635, 0.243, 1.0), "apple_music": (0.98, 0.20, 0.30),
}


def detect(title="", url=""):
    """Nome da marca ('youtube', 'whatsapp'...) ou None se não for um serviço conhecido."""
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        host = ""
    for part, brand in HOSTS:
        if host == part or host.endswith("." + part):
            return brand
    t = (title or "").strip().lower()
    if t in TITLE_EXACT:
        return TITLE_EXACT[t]
    for suffix, brand in TITLE_SUFFIXES:
        if t.endswith(suffix):
            return brand
    return None


# --- desenho (caixa 1×1; o chamador posiciona e escala) -----------------------------
def _round(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _youtube(cr):
    cr.set_source_rgb(*COLORS["youtube"])
    _round(cr, 0.0, 0.2, 1.0, 0.6, 0.18)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.move_to(0.40, 0.34)
    cr.line_to(0.40, 0.66)
    cr.line_to(0.68, 0.50)
    cr.close_path()
    cr.fill()


def _youtube_music(cr):
    cr.set_source_rgb(*COLORS["youtube_music"])
    cr.arc(0.5, 0.5, 0.5, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(0.035)
    cr.arc(0.5, 0.5, 0.36, 0, 2 * math.pi)
    cr.stroke()
    cr.move_to(0.42, 0.36)
    cr.line_to(0.42, 0.64)
    cr.line_to(0.66, 0.50)
    cr.close_path()
    cr.fill()


def _whatsapp(cr):
    cr.set_source_rgb(*COLORS["whatsapp"])
    cr.arc(0.5, 0.5, 0.5, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(0.055)
    cr.set_line_cap(1)
    cr.set_line_join(1)
    cx, cy, r = 0.5, 0.48, 0.30  # balão: círculo aberto no canto inferior esquerdo + cauda
    a1, a2 = math.radians(150), math.radians(120 + 360)
    cr.move_to(cx + r * math.cos(a1), cy + r * math.sin(a1))
    cr.arc(cx, cy, r, a1, a2)
    cr.line_to(0.21, 0.81)
    cr.close_path()
    cr.stroke()
    cr.set_line_width(0.07)  # telefone: traço curvo com as pontas do fone
    cr.move_to(0.40, 0.38)
    cr.curve_to(0.40, 0.52, 0.48, 0.60, 0.62, 0.62)
    cr.stroke()
    for x, y in ((0.40, 0.38), (0.62, 0.62)):
        cr.arc(x, y, 0.045, 0, 2 * math.pi)
        cr.fill()


def _twitch(cr):
    cr.set_source_rgb(*COLORS["twitch"])
    cr.move_to(0.12, 0.08)
    cr.line_to(0.92, 0.08)
    cr.line_to(0.92, 0.60)
    cr.line_to(0.66, 0.86)
    cr.line_to(0.46, 0.86)
    cr.line_to(0.30, 0.96)
    cr.line_to(0.30, 0.86)
    cr.line_to(0.12, 0.86)
    cr.close_path()
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    for x in (0.42, 0.62):
        _round(cr, x, 0.26, 0.07, 0.24, 0.02)
        cr.fill()


def _netflix(cr):
    cr.set_source_rgb(*COLORS["netflix"])
    _round(cr, 0.22, 0.06, 0.15, 0.88, 0.01)
    cr.fill()
    _round(cr, 0.63, 0.06, 0.15, 0.88, 0.01)
    cr.fill()
    cr.move_to(0.22, 0.06)
    cr.line_to(0.37, 0.06)
    cr.line_to(0.78, 0.94)
    cr.line_to(0.63, 0.94)
    cr.close_path()
    cr.fill()


def _telegram(cr):
    cr.set_source_rgb(*COLORS["telegram"])
    cr.arc(0.5, 0.5, 0.5, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.move_to(0.20, 0.50)
    cr.line_to(0.78, 0.26)
    cr.line_to(0.66, 0.74)
    cr.line_to(0.48, 0.60)
    cr.line_to(0.38, 0.70)
    cr.line_to(0.40, 0.56)
    cr.line_to(0.70, 0.34)
    cr.line_to(0.34, 0.54)
    cr.close_path()
    cr.fill()


def _deezer(cr):
    # cinco barras de alturas e cores diferentes (as cores da marca)
    bars = ((0.00, 0.78, (0.20, 0.82, 0.55)), (0.21, 0.58, (0.40, 0.60, 1.0)),
            (0.42, 0.40, (0.65, 0.25, 1.0)), (0.63, 0.58, (1.0, 0.30, 0.45)),
            (0.84, 0.78, (1.0, 0.70, 0.15)))
    for x, h, col in bars:
        cr.set_source_rgb(*col)
        _round(cr, x + 0.01, 1.0 - h, 0.15, h, 0.02)
        cr.fill()


def _apple_music(cr):
    cr.set_source_rgb(*COLORS["apple_music"])
    _round(cr, 0.0, 0.0, 1.0, 1.0, 0.24)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    cr.save()  # cabeça da nota (elipse inclinada)
    cr.translate(0.38, 0.70)
    cr.rotate(-0.35)
    cr.scale(1.0, 0.72)
    cr.arc(0, 0, 0.13, 0, 2 * math.pi)
    cr.restore()
    cr.fill()
    cr.set_line_width(0.06)
    cr.move_to(0.50, 0.68)  # haste e travessão
    cr.line_to(0.50, 0.26)
    cr.line_to(0.74, 0.22)
    cr.line_to(0.74, 0.58)
    cr.stroke()
    cr.save()
    cr.translate(0.62, 0.58)
    cr.rotate(-0.35)
    cr.scale(1.0, 0.72)
    cr.arc(0, 0, 0.13, 0, 2 * math.pi)
    cr.restore()
    cr.fill()


DRAW = {"youtube": _youtube, "youtube_music": _youtube_music, "whatsapp": _whatsapp,
        "twitch": _twitch, "netflix": _netflix, "telegram": _telegram,
        "deezer": _deezer, "apple_music": _apple_music}
