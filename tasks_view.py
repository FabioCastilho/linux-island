"""Página "Tarefas" da ilha expandida: uma lista curta para marcar e desmarcar."""
import math

from gi.repository import Gtk, Pango

from i18n import _
from icons import Glyph, glyph_button
from views import label
from widgets import DEFAULT_ACCENT

LIST_HEIGHT = 240


class CheckDot(Gtk.DrawingArea):
    """Círculo vazio; marcado vira cheio com o visto."""

    def __init__(self):
        super().__init__()
        self.done = False
        self.accent = DEFAULT_ACCENT
        self.set_size_request(20, 20)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        c = self.get_style_context().get_color(self.get_state_flags())
        if self.done:
            cr.set_source_rgb(*self.accent)
            cr.arc(10, 10, 8, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.set_line_width(1.8)
            cr.set_line_cap(1)
            cr.move_to(6, 10.5)
            cr.line_to(9, 13.5)
            cr.line_to(14, 7)
            cr.stroke()
        else:
            cr.set_source_rgba(c.red, c.green, c.blue, 0.45)
            cr.set_line_width(1.6)
            cr.arc(10, 10, 7.6, 0, 2 * math.pi)
            cr.stroke()


class TaskRow(Gtk.Box):
    def __init__(self, task, accent, on_toggle, on_remove):
        super().__init__(spacing=4)
        ctx = self.get_style_context()
        ctx.add_class("row-card")
        if task["done"]:
            ctx.add_class("done")
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_can_focus(False)
        btn.get_style_context().add_class("agenda-row")
        inner = Gtk.Box(spacing=10)
        dot = CheckDot()
        dot.done, dot.accent = task["done"], accent
        text = label("row-title", 0.0)
        text.set_text(task["text"])
        text.set_line_wrap(True)
        text.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        text.set_max_width_chars(38)
        if task["done"]:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_strikethrough_new(True))
            text.set_attributes(attrs)
        inner.pack_start(dot, False, False, 0)
        inner.pack_start(text, True, True, 0)
        btn.add(inner)
        btn.connect("clicked", lambda *_a: on_toggle(task["id"]))
        rm, _g = glyph_button("trash", 14, lambda: on_remove(task["id"]), _("Apagar"))
        self.pack_start(btn, True, True, 0)
        self.pack_start(rm, False, False, 0)


class TasksPage(Gtk.Box):
    WIDTH = 420

    def __init__(self, tasks, on_edit=lambda editing: None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.tasks = tasks
        self.accent = DEFAULT_ACCENT
        self.on_edit = on_edit  # avisa a janela: digitando, o teclado precisa chegar aqui
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        head.pack_start(Glyph("tasks", 16), False, False, 0)
        title = label("title")
        title.set_text(_("Tarefas"))
        head.pack_start(title, False, False, 0)
        self.count = label("dim small")
        head.pack_start(self.count, False, False, 0)
        self.clear_btn = Gtk.Button(label=_("Limpar concluídas"))
        self.clear_btn.set_can_focus(False)
        self.clear_btn.get_style_context().add_class("chip")
        self.clear_btn.connect("clicked", lambda *_a: self.tasks.clear_done())
        head.pack_end(self.clear_btn, False, False, 0)
        self.pack_start(head, False, False, 0)

        add = Gtk.Box(spacing=6)
        self.entry = Gtk.Entry(placeholder_text=_("Nova tarefa…"))
        self.entry.get_style_context().add_class("quick-entry")
        self.entry.set_max_length(200)
        self.entry.connect("activate", lambda *_a: self._add())
        self.entry.connect("focus-in-event", lambda *_a: self.on_edit(True) or False)
        self.entry.connect("focus-out-event", lambda *_a: self.on_edit(False) or False)
        plus, _g = glyph_button("plus", 16, self._add, _("Adicionar"))
        add.pack_start(self.entry, True, True, 0)
        add.pack_start(plus, False, False, 0)
        self.pack_start(add, False, False, 0)

        self.empty = label("dim", 0.5)
        self.empty.set_text(_("Tudo em dia"))
        self.empty.set_margin_top(10)
        self.empty.set_margin_bottom(10)
        self.listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_max_content_height(LIST_HEIGHT)
        self.scroll.add(self.listbox)
        for w in (self.empty, self.scroll, self.clear_btn):
            w.set_no_show_all(True)  # a janela chama show_all(); a visibilidade é de update()
        self.pack_start(self.empty, False, False, 0)
        self.pack_start(self.scroll, False, False, 0)

        tasks.connect(self.update)
        self.connect("map", lambda *_a: self.update())
        self.connect("unmap", lambda *_a: self.on_edit(False))
        self.update()

    def editing(self):
        return self.entry.has_focus()

    def set_accent(self, accent):
        self.accent = accent

    def _add(self):
        if self.tasks.add(self.entry.get_text()):
            self.entry.set_text("")

    def update(self):
        for c in self.listbox.get_children():
            self.listbox.remove(c)
        for t in self.tasks.items:
            self.listbox.pack_start(
                TaskRow(t, self.accent, self.tasks.toggle, self.tasks.remove), False, False, 0)
        self.listbox.show_all()
        # a janela da ilha fica no tamanho mínimo: o scroll só ocupa o que a lista pede, até o teto
        nat = self.listbox.get_preferred_height()[1]
        self.scroll.set_min_content_height(min(nat, LIST_HEIGHT))
        pending = self.tasks.pending
        self.count.set_text(f"· {pending}" if pending else "")
        has = bool(self.tasks.items)
        self.empty.set_visible(not has)
        self.scroll.set_visible(has)
        self.clear_btn.set_visible(any(t["done"] for t in self.tasks.items))
