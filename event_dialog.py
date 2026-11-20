"""Janela "Novo evento": formulário + confirmação antes de enviar ao Google.

É uma janela normal (não a ilha) porque só ela recebe teclado de forma confiável.
Duas etapas: preencher -> conferir o resumo -> "Criar evento". Nada é enviado antes disso.
"""
from datetime import datetime, timedelta

from gi.repository import GLib, Gtk

from agenda import build_event, parse_date, parse_time
from i18n import _, short_date


class EventDialog(Gtk.Window):
    def __init__(self, agenda):
        super().__init__(title=_("Novo evento"))
        self.agenda = agenda
        self.body = None
        self.set_default_size(380, -1)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        now = datetime.now().astimezone()
        nxt = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        self.stack = Gtk.Stack()
        self.add(self.stack)

        # etapa 1: formulário
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("top", "bottom", "start", "end"):
            getattr(form, f"set_margin_{side}")(18)
        grid = Gtk.Grid(row_spacing=8, column_spacing=10)
        self.title_entry = Gtk.Entry(placeholder_text=_("Título"), hexpand=True)
        self.title_entry.set_max_length(200)
        self.date_entry = Gtk.Entry(text=f"{now:%d/%m/%Y}", hexpand=True,
                                    placeholder_text=_("hoje, amanhã, 25/12…"))
        self.time_entry = Gtk.Entry(text=f"{nxt:%H:%M}", hexpand=True,
                                    placeholder_text="14:30")
        self.dur = Gtk.SpinButton.new_with_range(5, 24 * 60, 15)
        self.dur.set_value(60)
        self.all_day = Gtk.CheckButton(label=_("Dia inteiro"))
        self.all_day.connect("toggled", self._on_all_day)
        rows = ((_("Título"), self.title_entry), (_("Data"), self.date_entry),
                (_("Início"), self.time_entry), (_("Duração (min)"), self.dur))
        for i, (text, widget) in enumerate(rows):
            lb = Gtk.Label(label=text, xalign=0)
            lb.get_style_context().add_class("dim-label")
            grid.attach(lb, 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        grid.attach(self.all_day, 1, len(rows), 1, 1)
        form.pack_start(grid, False, False, 0)
        self.error = Gtk.Label(xalign=0, wrap=True)
        self.error.get_style_context().add_class("error")
        form.pack_start(self.error, False, False, 0)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=_("Cancelar"))
        cancel.connect("clicked", lambda *_a: self.destroy())
        self.review_btn = Gtk.Button(label=_("Revisar"))
        self.review_btn.get_style_context().add_class("suggested-action")
        self.review_btn.connect("clicked", lambda *_a: self._review())
        buttons.pack_start(cancel, False, False, 0)
        buttons.pack_start(self.review_btn, False, False, 0)
        form.pack_start(buttons, False, False, 0)
        self.stack.add_named(form, "form")

        # etapa 2: conferência
        confirm = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(confirm, f"set_margin_{side}")(18)
        ask = Gtk.Label(label=_("Criar este evento na sua agenda principal do Google?"),
                        xalign=0, wrap=True)
        self.summary = Gtk.Label(xalign=0, wrap=True)
        self.summary.set_selectable(False)
        self.result = Gtk.Label(xalign=0, wrap=True)
        row2 = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.back_btn = Gtk.Button(label=_("Voltar"))
        self.back_btn.connect("clicked", lambda *_a: self.stack.set_visible_child_name("form"))
        self.create_btn = Gtk.Button(label=_("Criar evento"))
        self.create_btn.get_style_context().add_class("suggested-action")
        self.create_btn.connect("clicked", lambda *_a: self._create())
        row2.pack_start(self.back_btn, False, False, 0)
        row2.pack_start(self.create_btn, False, False, 0)
        for w in (ask, self.summary, self.result, row2):
            confirm.pack_start(w, False, False, 0)
        self.stack.add_named(confirm, "confirm")

        self.title_entry.connect("activate", lambda *_a: self._review())
        self.show_all()
        self.title_entry.grab_focus()

    def _on_all_day(self, box):
        timed = not box.get_active()
        self.time_entry.set_sensitive(timed)
        self.dur.set_sensitive(timed)

    def _review(self):
        today = datetime.now().astimezone().date()
        try:
            day = parse_date(self.date_entry.get_text(), today)
        except ValueError:
            return self._fail(_("Data inválida. Use hoje, amanhã, 25/12 ou 25/12/2026."))
        start = None
        if not self.all_day.get_active():
            try:
                start = parse_time(self.time_entry.get_text())
            except ValueError:
                return self._fail(_("Hora inválida. Use 14:30."))
        try:
            self.body = build_event(self.title_entry.get_text(), day, start,
                                    int(self.dur.get_value()))
        except ValueError:
            return self._fail(_("Informe um título (até 200 caracteres) e uma duração válida."))
        self.error.set_text("")
        title = self.body["summary"]
        if start is None:
            when = f"{short_date(day)} · {_('dia inteiro')}"
        else:
            end = datetime.fromisoformat(self.body["end"]["dateTime"])
            when = f"{short_date(day)} · {start:%H:%M}–{end:%H:%M}"
        self.summary.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>\n"
                                f"{GLib.markup_escape_text(when)}")
        self.result.set_text("")
        self.create_btn.set_sensitive(True)
        self.stack.set_visible_child_name("confirm")

    def _fail(self, text):
        self.error.set_text(text)

    def _create(self):
        self.create_btn.set_sensitive(False)  # evita clique duplo = evento duplicado
        self.back_btn.set_sensitive(False)
        self.result.set_text(_("Criando…"))
        self.agenda.create_event(self.body, self._done)

    def _done(self, ok, msg):
        if not self.get_visible():  # janela fechada no meio
            return False
        if ok:
            self.result.set_text(_("Evento criado!"))
            GLib.timeout_add(1200, lambda: self.destroy() or False)
        else:
            self.result.set_text(msg)
            self.back_btn.set_sensitive(True)
        return False
