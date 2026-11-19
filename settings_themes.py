"""Grupo "Temas" da janela de configurações: escolher, salvar, importar, exportar e apagar.

Mixin de settings.Settings: usa self.cfg, self._group, self._row e self.get_application/self.
"""
import os

from gi.repository import GLib, Gtk

import themes
from config import rgba
from i18n import _

SWATCH = (64, 26)


def _swatch(values, cfg):
    """Pílula pequena com o fundo, o texto e o destaque do tema."""
    bg = rgba(values.get("bg_color", cfg["bg_color"]))
    fg = rgba(values.get("text_color", cfg["text_color"]))
    ac = rgba(values.get("accent_color", cfg["accent_color"]))
    area = Gtk.DrawingArea()
    area.set_size_request(*SWATCH)

    def draw(_w, cr):
        w, h = area.get_allocated_width(), area.get_allocated_height()
        r = h / 2
        cr.set_source_rgba(bg.red, bg.green, bg.blue, max(bg.alpha, 0.35))
        cr.arc(r, r, r, 1.5708, 4.7124)
        cr.arc(w - r, r, r, -1.5708, 1.5708)
        cr.close_path()
        cr.fill()
        cr.set_source_rgb(ac.red, ac.green, ac.blue)
        cr.arc(w - r, r, 4, 0, 6.2832)
        cr.fill()
        cr.set_source_rgb(fg.red, fg.green, fg.blue)
        cr.rectangle(r - 2, r - 1.5, w / 2 - r, 3)
        cr.fill()

    area.connect("draw", draw)
    return area


class SettingsThemesMixin:
    # --- construção -------------------------------------------------------------
    def _themes_group(self, page):
        lb = self._group(page, "Temas")
        self._theme_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                       max_children_per_line=5, column_spacing=8, row_spacing=8)
        for side in ("top", "bottom", "start", "end"):
            getattr(self._theme_flow, f"set_margin_{side}")(10)
        lb.add(self._theme_flow)

        self._theme_status = Gtk.Label(xalign=0)
        self._theme_status.get_style_context().add_class("dim-label")
        self._theme_status.set_margin_start(12)
        self._theme_status.set_margin_bottom(8)
        lb.add(self._theme_status)

        box = Gtk.Box(spacing=6)
        self._theme_entry = Gtk.Entry(placeholder_text=_("Nome do tema"))
        self._theme_entry.set_max_length(themes.MAX_NAME)
        self._theme_entry.set_width_chars(16)
        self._theme_entry.connect("activate", lambda *_a: self._save_theme())
        save = Gtk.Button(label=_("Salvar"))
        save.connect("clicked", lambda *_a: self._save_theme())
        box.pack_start(self._theme_entry, False, False, 0)
        box.pack_start(save, False, False, 0)
        self._row(lb, "Salvar o visual atual como tema", box,
                  "Guarda cores, formas, equalizador, capa e animações. Fica em "
                  "~/.config/linux-island/themes")
        imp = Gtk.Button(label=_("Importar…"))
        imp.connect("clicked", lambda *_a: self._import_theme())
        self._row(lb, "Importar um tema", imp, "Arquivo .json de um tema exportado")

        self._mine = self._group(page, "Meus temas")
        self._themes_changed()
        lb.show_all()

    # --- tema automático ----------------------------------------------------------
    def _theme_combo(self, key):
        """Lista de temas (embutidos + seus) ligada a uma chave da configuração."""
        combo = Gtk.ComboBoxText()
        hid = combo.connect("changed", lambda c: c.get_active_id()
                            and self.cfg.set(key, c.get_active_id()))
        self._theme_combos = getattr(self, "_theme_combos", []) + [(combo, key, hid)]
        self._fill_theme_combo(combo, key, hid)
        self._sync[key] = lambda: combo.set_active_id(self.cfg[key])
        return combo

    def _fill_theme_combo(self, combo, key, hid):
        combo.handler_block(hid)  # repovoar não pode escrever na configuração
        combo.remove_all()
        for t in themes.all_themes():
            combo.append(t["name"], _(t["name"]) if t["builtin"] else t["name"])
        combo.set_active_id(self.cfg[key])
        combo.handler_unblock(hid)

    def _auto_theme_group(self, page):
        lb = self._group(page, "Tema automático")
        modes = [("off", "Desligado"), ("kde", "Seguir o tema do KDE"), ("schedule", "Por horário")]
        self._row(lb, "Trocar de tema sozinho", self._choice("theme_auto", modes),
                  "No modo KDE, troca quando o sistema muda entre claro e escuro. Se você "
                  "escolher outro tema no meio do período, ele fica até a próxima troca")
        self._row(lb, "Tema claro", self._theme_combo("theme_light"))
        self._row(lb, "Tema escuro", self._theme_combo("theme_dark"))
        hours = [self._row(lb, "Escuro a partir das (h)", self._spin("theme_dark_from_h", 0, 23),
                           "Só no modo por horário"),
                 self._row(lb, "Escuro até as (h)", self._spin("theme_dark_to_h", 0, 23))]

        def show_hours():
            for r in hours:
                r.set_sensitive(self.cfg["theme_auto"] == "schedule")

        show_hours()
        prev = self._sync["theme_auto"]
        self._sync["theme_auto"] = lambda: (prev(), show_hours())
        lb.show_all()

    def _themes_changed(self):
        """Refaz os botões, a lista dos meus temas e o texto do tema atual."""
        for combo, key, hid in getattr(self, "_theme_combos", []):
            self._fill_theme_combo(combo, key, hid)
        cfg = self.cfg
        for c in self._theme_flow.get_children():
            self._theme_flow.remove(c)
        for theme in themes.all_themes():
            self._theme_flow.add(self._theme_button(theme))
        self._theme_flow.show_all()

        for row in self._mine.get_children():
            self._mine.remove(row)
        mine = themes.user_themes()
        if not mine:
            lb = Gtk.Label(label=_("Você ainda não salvou nenhum tema"), xalign=0)
            lb.get_style_context().add_class("dim-label")
            lb.set_margin_top(10)
            lb.set_margin_bottom(10)
            lb.set_margin_start(12)
            self._mine.add(lb)
        for theme in mine:
            self._mine_row(theme)
        self._mine.show_all()
        self._update_theme_status()

    def _theme_button(self, theme):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(_swatch(theme["values"], self.cfg), False, False, 0)
        name = Gtk.Label(label=theme["name"] if not theme["builtin"] else _(theme["name"]))
        name.set_max_width_chars(10)
        name.set_ellipsize(3)  # Pango.EllipsizeMode.END
        box.pack_start(name, False, False, 0)
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.add(box)
        btn.set_tooltip_text(theme["name"])
        btn.connect("clicked", lambda *_a: themes.apply(self.cfg, theme))
        return btn

    def _mine_row(self, theme):
        box = Gtk.Box(spacing=6)
        export = Gtk.Button(label=_("Exportar…"))
        export.connect("clicked", lambda *_a: self._export_theme(theme))
        delete = Gtk.Button(label=_("Apagar"))
        armed = {"timer": None}

        def disarm():
            armed["timer"] = None
            delete.set_label(_("Apagar"))
            return False

        def on_delete(*_a):
            if armed["timer"] is None:   # primeiro clique só pede confirmação
                delete.set_label(_("Confirmar?"))
                armed["timer"] = GLib.timeout_add_seconds(3, disarm)
                return
            GLib.source_remove(armed["timer"])
            if themes.delete_user(theme):
                self._themes_changed()

        delete.connect("clicked", on_delete)
        box.pack_start(export, False, False, 0)
        box.pack_start(delete, False, False, 0)
        row = self._row(self._mine, theme["name"], box)
        row.set_tooltip_text(theme["name"])

    # --- ações --------------------------------------------------------------------
    def _update_theme_status(self):
        name = themes.active_name(self.cfg, themes.all_themes())
        self._theme_status.set_text(_("Tema atual: {name}").format(name=_(name))
                                    if name else _("Tema atual: personalizado"))

    def _flash_theme_status(self, text):
        self._theme_status.set_text(text)
        GLib.timeout_add_seconds(4, lambda: (self._update_theme_status(), False)[1])

    def _save_theme(self):
        name = self._theme_entry.get_text().strip()
        if not name:
            return
        if name.lower() in {t["name"].lower() for t in themes.BUILTIN}:
            self._flash_theme_status(_("Já existe um tema embutido com esse nome"))
            return
        try:
            themes.save_user(themes.snapshot(self.cfg, name))
        except OSError as e:
            self._flash_theme_status(_("Não deu para salvar: {e}").format(e=e.strerror or e))
            return
        self._theme_entry.set_text("")
        self._themes_changed()
        self._flash_theme_status(_("Tema “{name}” salvo").format(name=name))

    def _json_filter(self):
        f = Gtk.FileFilter()
        f.set_name("JSON")
        f.add_pattern("*.json")
        return f

    def _import_theme(self):
        dlg = Gtk.FileChooserNative.new(_("Importar tema"), self, Gtk.FileChooserAction.OPEN,
                                        _("Importar"), _("Cancelar"))
        dlg.add_filter(self._json_filter())
        self._chooser = dlg  # mantém vivo enquanto aberto

        def done(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                theme = themes.import_from(d.get_filename())
                self._themes_changed()
                self._flash_theme_status(
                    _("Tema “{name}” importado").format(name=theme["name"]) if theme
                    else _("Esse arquivo não é um tema válido"))
            self._chooser = None

        dlg.connect("response", done)
        dlg.show()

    def _export_theme(self, theme):
        dlg = Gtk.FileChooserNative.new(_("Exportar tema"), self, Gtk.FileChooserAction.SAVE,
                                        _("Exportar"), _("Cancelar"))
        dlg.add_filter(self._json_filter())
        dlg.set_current_name(themes.slug(theme["name"]) + ".json")
        dlg.set_do_overwrite_confirmation(True)
        self._chooser = dlg

        def done(d, response):
            if response == Gtk.ResponseType.ACCEPT:
                try:
                    themes.export_to(theme, d.get_filename())
                    self._flash_theme_status(_("Tema exportado para {f}").format(
                        f=os.path.basename(d.get_filename())))
                except OSError as e:
                    self._flash_theme_status(_("Não deu para exportar: {e}").format(
                        e=e.strerror or e))
            self._chooser = None

        dlg.connect("response", done)
        dlg.show()
