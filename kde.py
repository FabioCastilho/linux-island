"""Lê do KDE (arquivo ~/.config/kdeglobals) a cor de destaque e se o esquema é claro ou escuro.

Funções puras que recebem o caminho, para os testes usarem arquivos de mentira. O KDE reescreve
esse arquivo quando você troca o tema ou a cor de destaque, então basta observá-lo.
"""
import os

from gi.repository import GLib

PATH = os.path.join(GLib.get_user_config_dir(), "kdeglobals")


def read_sections(path=PATH):
    """{seção: {chave: valor}} do arquivo INI do KDE. {} se não existir ou não der para ler."""
    out, cur = {}, None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("[") and line.endswith("]"):
                    cur = out.setdefault(line[1:-1], {})
                elif cur is not None and "=" in line and not line.startswith("#"):
                    k, _sep, v = line.partition("=")
                    cur[k.strip()] = v.strip()
    except OSError:
        return {}
    return out


def parse_rgb(text):
    """'104,107,111' -> (0.41, 0.42, 0.44); None se não for uma cor válida."""
    try:
        parts = [int(p) for p in (text or "").split(",")[:3]]
        if len(parts) == 3 and all(0 <= p <= 255 for p in parts):
            return tuple(p / 255 for p in parts)
    except ValueError:
        pass
    return None


def accent(path=PATH):
    """Cor de destaque do KDE (r, g, b em 0..1). Sem ela, a cor de seleção do esquema."""
    s = read_sections(path)
    c = parse_rgb(s.get("General", {}).get("AccentColor"))
    return c or parse_rgb(s.get("Colors:Selection", {}).get("BackgroundNormal"))


def accent_spec(path=PATH):
    """A mesma cor no formato da configuração: 'rgb(104,107,111)'."""
    c = accent(path)
    return "rgb({},{},{})".format(*(round(x * 255) for x in c)) if c else None


def is_dark(path=PATH):
    """True se o fundo das janelas do esquema atual é escuro; None se não deu para saber."""
    c = parse_rgb(read_sections(path).get("Colors:Window", {}).get("BackgroundNormal"))
    if c is None:
        return None
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) < 0.5
