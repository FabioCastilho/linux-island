"""Quais páginas a ilha expandida tem, em que ordem e quais estão escondidas.

Função pura (sem GTK) para a ordem e a visibilidade poderem ser testadas e usadas pela
configuração e pela janela.
"""
ALL_PAGES = ("home", "media", "water", "agenda", "notifs", "focus", "tasks", "camera", "bluetooth",
             "system", "claude")
LEGACY = ("ia", "sessions")  # páginas que viraram "claude"; ainda valem em configs antigas
ALWAYS_SHOWN = ("home",)  # sem a página inicial a ilha não teria o que mostrar ao expandir


def split(spec):
    return [p.strip() for p in (spec or "").split(",") if p.strip()]


def valid_spec(spec):
    """Validador do config: texto com nomes de páginas conhecidas, sem repetir."""
    if not isinstance(spec, str) or len(spec) > 200:
        return False
    names = split(spec)
    return all(n in ALL_PAGES or n in LEGACY for n in names) and len(names) == len(set(names))


def order(spec):
    """Ordem completa: a pedida primeiro, depois as que faltam na ordem padrão."""
    wanted = [p for p in split(spec) if p in ALL_PAGES]
    seen = list(dict.fromkeys(wanted))
    return seen + [p for p in ALL_PAGES if p not in seen]


def visible(order_spec, hidden_spec):
    hidden = {p for p in split(hidden_spec) if p not in ALWAYS_SHOWN}
    return [p for p in order(order_spec) if p not in hidden]


def move(order_spec, page, step):
    """Nova ordem (texto) com `page` movida `step` posições (-1 sobe, +1 desce)."""
    pages = order(order_spec)
    i = pages.index(page)
    j = max(0, min(len(pages) - 1, i + step))
    pages.insert(j, pages.pop(i))
    return ",".join(pages)
