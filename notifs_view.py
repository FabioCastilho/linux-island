"""Página "Notificações" da ilha expandida: as últimas notificações, com o app de origem."""
from gi.repository import Gio, Gtk

from claude_sessions import ago
from i18n import _
from icons import Glyph, glyph_button
from views import clip, label

MAX_SHOWN = 30
LIST_HEIGHT = 300


class NotifRow(Gtk.Button):
    def __init__(self, entry, on_open):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.set_can_focus(False)
        ctx = self.get_style_context()
        ctx.add_class("agenda-row")
        n = entry.n
        box = Gtk.Box(spacing=10)
        img = Gtk.Image()
        if n.icon is not None:
            img.set_from_gicon(n.icon, Gtk.IconSize.BUTTON)
        else:
            img.set_from_icon_name("preferences-system-notifications-symbolic", Gtk.IconSize.BUTTON)
        img.set_pixel_size(22)
        img.set_valign(Gtk.Align.START)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        top = Gtk.Box(spacing=6)
        title = label("title row-title", 0.0)
        title.set_text(clip(n.summary, 40))
        app = label("dim small")
        app.set_text(clip(n.app, 18))
        age = label("dim small", 1.0)
        age.set_text(ago(entry.ts))
        top.pack_start(title, False, False, 0)
        top.pack_start(app, False, False, 0)
        top.pack_end(age, False, False, 0)
        texts.pack_start(top, False, False, 0)
        if n.body:
            body = label("dim small")
            body.set_text(clip(n.body, 64))
            texts.pack_start(body, False, False, 0)
        if not entry.read:
            ctx.add_class("unread")
        box.pack_start(img, False, False, 0)
        box.pack_start(texts, True, True, 0)
        self.add(box)
        self.set_sensitive(True)
        self.connect("clicked", lambda *_a: on_open(n))
        self.set_tooltip_text(_("Abrir o app") if n.desktop_entry else n.body or n.summary)


class NotifsPage(Gtk.Box):
    WIDTH = 420

    def __init__(self, history, on_clear=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.history = history
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        head.pack_start(Glyph("bell", 16), False, False, 0)
        title = label("title")
        title.set_text(_("Notificações"))
        head.pack_start(title, False, False, 0)
        self.count = label("dim small")
        head.pack_start(self.count, False, False, 0)
        clear, _g = glyph_button("trash", 15, self.history.clear, _("Limpar tudo"))
        head.pack_end(clear, False, False, 0)
        self.clear_btn = clear
        self.pack_start(head, False, False, 0)

        self.empty = label("dim", 0.5)
        self.empty.set_text(_("Nenhuma notificação por aqui"))
        self.empty.set_margin_top(18)
        self.empty.set_margin_bottom(18)
        self.listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_max_content_height(LIST_HEIGHT)
        self.scroll.add(self.listbox)
        for w in (self.empty, self.scroll):
            w.set_no_show_all(True)  # a janela chama show_all(); a visibilidade é de update()
        self.pack_start(self.empty, False, False, 0)
        self.pack_start(self.scroll, False, False, 0)

        history.connect(self.update)
        self.connect("map", lambda *_a: self.update())
        # ver a página conta como ler, mas só ao sair: enquanto ela está aberta o destaque fica
        self.connect("unmap", lambda *_a: self.history.mark_read())
        self.update()

    def update(self):
        for c in self.listbox.get_children():
            self.listbox.remove(c)
        items = self.history.items[:MAX_SHOWN]
        for e in items:
            self.listbox.pack_start(NotifRow(e, self._open), False, False, 0)
        self.listbox.show_all()
        # a janela da ilha fica no tamanho mínimo: o scroll só ocupa o que a lista pede, até o teto
        nat = self.listbox.get_preferred_height()[1]
        self.scroll.set_min_content_height(min(nat, LIST_HEIGHT))
        n = len(self.history.items)
        self.count.set_text(f"· {n}" if n else "")
        self.empty.set_visible(not items)
        self.scroll.set_visible(bool(items))
        self.clear_btn.set_sensitive(bool(items))

    @staticmethod
    def _open(n):
        if not n.desktop_entry:
            return
        try:
            info = Gio.DesktopAppInfo.new(n.desktop_entry + ".desktop")
        except TypeError:
            info = None
        if info is not None:
            info.launch([], None)
