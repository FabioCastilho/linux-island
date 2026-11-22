"""Temas da ilha: um conjunto de chaves da configuração que se aplica de uma vez.

Os temas embutidos ficam aqui; os do usuário são arquivos JSON em
~/.config/linux-island/themes/ e podem ser importados e exportados. Sem GTK além do
necessário para validar cores, para os testes rodarem sem janela.

Formato do arquivo:  {"version": 1, "name": "Meu tema", "values": {"bg_color": "...", ...}}
Um tema só mexe nas chaves que ele traz (os embutidos antigos mudam só as cores e o vidro, sem
desligar o seu entalhe, por exemplo); um tema salvo do visual atual traz todas.
"""
import json
import os
import re

from gi.repository import GLib

from config import SCHEMA
from logutil import warn

USER_DIR = os.path.join(GLib.get_user_config_dir(), "linux-island", "themes")
VERSION = 1
MAX_NAME = 40
MAX_FILE_BYTES = 64 * 1024   # um tema é pequeno; recusa arquivos enormes

# chaves que um tema pode carregar (o resto da configuração é do usuário, não do tema)
THEME_KEYS = (
    "bg_color", "text_color", "accent_auto", "accent_color", "border", "radius_expanded",
    "radius_compact", "glass_style", "glass_sheen", "glass_blur", "notch_style", "notch_ear", "eq_style",
    "art_glow", "animations", "color_water", "color_meeting", "color_focus", "color_claude",
)

_ALERTS = {"color_water": "rgb(41,158,245)", "color_meeting": "rgb(167,139,250)",
           "color_focus": "rgb(237,102,82)", "color_claude": "rgb(217,119,87)"}


def _t(name, bg, fg, auto, accent, **extra):
    return {"name": name, "builtin": True,
            "values": {"bg_color": bg, "text_color": fg, "accent_auto": auto,
                       "accent_color": accent, "glass_style": extra.pop("glass", False),
                       **_ALERTS, **extra}}


BUILTIN = [
    _t("Clássico", "rgba(0,0,0,1)", "rgb(255,255,255)", True, "rgb(30,215,96)"),
    _t("Vidro", "rgba(20,20,28,0.72)", "rgb(255,255,255)", True, "rgb(30,215,96)"),
    _t("Claro", "rgba(246,246,248,1)", "rgb(20,20,24)", False, "rgb(0,122,255)"),
    _t("Spotify", "rgba(18,18,18,1)", "rgb(255,255,255)", False, "rgb(30,215,96)"),
    _t("Grafite", "rgba(43,46,52,1)", "rgb(230,232,236)", False, "rgb(255,159,67)"),
    _t("Vidro Apple", "rgba(30,32,44,0.50)", "rgb(255,255,255)", True, "rgb(10,132,255)",
       glass=True),
    # o "Escuro" do mac-dock: cinza neutro translúcido sobre o blur do KWin
    _t("Escuro", "rgba(26,26,31,0.55)", "rgb(255,255,255)", True, "rgb(10,132,255)",
       glass=True, glass_blur=True, glass_sheen=False),
    # novos: levam também as cores de alerta, o equalizador e a capa
    _t("Claude", "rgba(31,27,24,1)", "rgb(245,237,229)", False, "rgb(217,119,87)",
       eq_style="mirror", art_glow="glow", color_water="rgb(96,165,250)",
       color_meeting="rgb(192,160,255)", color_focus="rgb(240,120,90)",
       color_claude="rgb(217,119,87)"),
    _t("Oceano", "rgba(10,28,44,1)", "rgb(226,240,250)", False, "rgb(56,189,248)",
       eq_style="wave", art_glow="glow", color_water="rgb(56,189,248)",
       color_meeting="rgb(167,139,250)", color_focus="rgb(251,146,110)",
       color_claude="rgb(251,170,110)"),
]


def slug(name):
    """Nome de arquivo seguro a partir do nome do tema (nunca sai da pasta de temas)."""
    s = re.sub(r"[^a-z0-9_-]+", "-", (name or "").lower().strip()).strip("-")
    return s[:MAX_NAME] or "tema"


def clean_values(values):
    """Só as chaves de tema, com valor válido pelo mesmo validador da configuração."""
    out = {}
    if not isinstance(values, dict):
        return out
    for key in THEME_KEYS:
        if key in values and SCHEMA[key][1](values[key]):
            out[key] = values[key]
    return out


def parse_theme(data, builtin=False):
    """dict do JSON -> tema, ou None se não servir (sem nome, sem nenhuma chave válida)."""
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    values = clean_values(data.get("values"))
    if not isinstance(name, str) or not name.strip() or not values:
        return None
    return {"name": name.strip()[:MAX_NAME], "values": values, "builtin": builtin}


def read_file(path):
    """Lê um arquivo de tema. None (com aviso no log) se for inválido ou grande demais."""
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            warn(f"tema ignorado (arquivo grande demais): {os.path.basename(path)}")
            return None
        with open(path) as f:
            theme = parse_theme(json.load(f))
    except (OSError, ValueError) as e:
        warn(f"tema ilegível: {os.path.basename(path)}", e)
        return None
    if theme is None:
        warn(f"tema inválido: {os.path.basename(path)}")
    return theme


def user_themes(directory=None):
    d = directory or USER_DIR
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for fn in names:
        if fn.endswith(".json"):
            t = read_file(os.path.join(d, fn))
            if t:
                t["file"] = os.path.join(d, fn)
                out.append(t)
    return out


def all_themes(directory=None):
    """Embutidos primeiro; um tema do usuário com o mesmo nome de um embutido o substitui
    apenas na lista (o arquivo dele continua separado)."""
    return [dict(t) for t in BUILTIN] + user_themes(directory)


def apply(cfg, theme):
    """Aplica as chaves do tema à configuração (ao vivo e salvando)."""
    for key, value in theme["values"].items():
        cfg.set(key, value)


def snapshot(cfg, name):
    """Tema com o visual de agora (todas as chaves de tema)."""
    return {"name": name.strip()[:MAX_NAME], "builtin": False,
            "values": {k: cfg[k] for k in THEME_KEYS}}


def active_name(cfg, themes):
    """Nome do primeiro tema cujos valores batem com a configuração; None = personalizado."""
    for t in themes:
        if all(cfg[k] == v for k, v in t["values"].items()):
            return t["name"]
    return None


def save_user(theme, directory=None):
    """Grava em <pasta>/<slug>.json (substitui o de mesmo nome). Devolve o caminho."""
    d = directory or USER_DIR
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, slug(theme["name"]) + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"version": VERSION, "name": theme["name"], "values": theme["values"]}, f,
                  indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def delete_user(theme, directory=None):
    """Apaga só arquivos dentro da pasta de temas (confere o caminho antes)."""
    d = os.path.realpath(directory or USER_DIR)
    path = os.path.realpath(theme.get("file", ""))
    if os.path.dirname(path) == d and path.endswith(".json") and os.path.exists(path):
        os.remove(path)
        return True
    return False


def export_to(theme, path):
    with open(path, "w") as f:
        json.dump({"version": VERSION, "name": theme["name"], "values": theme["values"]}, f,
                  indent=2, ensure_ascii=False)


def import_from(path, directory=None):
    """Importa um arquivo para a pasta de temas. Devolve o tema ou None se inválido."""
    theme = read_file(path)
    if theme is None:
        return None
    save_user(theme, directory)
    return theme
