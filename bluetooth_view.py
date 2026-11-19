"""Página "Bluetooth" da ilha expandida: dispositivos pareados, bateria, conectar/desconectar."""
from gi.repository import Gtk

from i18n import _
from icons import Glyph
from views import clip, label

LOW_BATTERY = 20


class DeviceRow(Gtk.Box):
    def __init__(self, device, busy, on_toggle):
        super().__init__(spacing=10)
        self.get_style_context().add_class("row-card")
        img = Gtk.Image.new_from_icon_name(self._icon(device["icon"]), Gtk.IconSize.BUTTON)
        img.set_pixel_size(22)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name = label("title", 0.0)
        name.set_text(clip(device["name"], 30))
        sub = label("dim small", 0.0)
        parts = [_("Conectado") if device["connected"] else _("Desconectado")]
        if device["battery"] is not None:
            parts.append(f"{device['battery']}%")
        sub.set_text(" · ".join(parts))
        if device["battery"] is not None and device["battery"] <= LOW_BATTERY:
            sub.get_style_context().add_class("over")   # bateria baixa: usa a cor de alerta
        texts.pack_start(name, False, False, 0)
        texts.pack_start(sub, False, False, 0)
        btn = Gtk.Button(label=(_("Conectando…") if busy and not device["connected"]
                                else _("Desconectando…") if busy
                                else _("Desconectar") if device["connected"] else _("Conectar")))
        btn.set_can_focus(False)
        btn.set_sensitive(not busy)
        btn.get_style_context().add_class("chip")
        if device["connected"]:
            btn.get_style_context().add_class("active")
        btn.connect("clicked", lambda *_a: on_toggle(device))
        self.pack_start(img, False, False, 0)
        self.pack_start(texts, True, True, 0)
        self.pack_start(btn, False, False, 0)

    @staticmethod
    def _icon(name):
        """O BlueZ informa nomes de ícone do tema (audio-headphones, input-mouse...)."""
        name = name or "bluetooth"
        return name if name.endswith("-symbolic") else name + "-symbolic"


class BluetoothPage(Gtk.Box):
    WIDTH = 420

    def __init__(self, bt):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.bt = bt
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        head.pack_start(Glyph("bluetooth", 16), False, False, 0)
        title = label("title")
        title.set_text("Bluetooth")
        head.pack_start(title, False, False, 0)
        self.power = Gtk.Button()
        self.power.set_can_focus(False)
        self.power.get_style_context().add_class("chip")
        self.power.connect("clicked", self._on_power)
        head.pack_end(self.power, False, False, 0)
        self.pack_start(head, False, False, 0)

        self.empty = label("dim", 0.5)
        self.empty.set_margin_top(14)
        self.empty.set_margin_bottom(14)
        self.empty.set_no_show_all(True)
        self.listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.error = label("dim small", 0.0)
        self.error.set_line_wrap(True)
        self.error.set_no_show_all(True)
        for w in (self.empty, self.listbox, self.error):
            self.pack_start(w, False, False, 0)
        self.update()

    def show_error(self, text):
        self.error.set_text(text)
        self.error.show()

    def _on_power(self, *_a):
        adapter = self.bt.adapter
        if adapter is not None:
            self.bt.set_powered(not adapter["powered"])

    def update(self):
        bt = self.bt
        self.error.hide()
        for c in self.listbox.get_children():
            self.listbox.remove(c)
        adapter = bt.adapter
        on = bool(adapter and adapter["powered"])
        self.power.set_sensitive(adapter is not None)
        self.power.set_label(_("Ligado") if on else _("Desligado"))
        ctx = self.power.get_style_context()
        (ctx.add_class if on else ctx.remove_class)("active")
        if adapter is None:
            self.empty.set_text(_("Nenhum adaptador Bluetooth encontrado"))
        elif not adapter["powered"]:
            self.empty.set_text(_("Bluetooth desligado"))
        elif not bt.devices:
            self.empty.set_text(_("Nenhum dispositivo pareado"))
        shown = bool(adapter and adapter["powered"] and bt.devices)
        for d in bt.devices if shown else []:
            self.listbox.pack_start(DeviceRow(d, d["path"] in bt.busy, bt.toggle_device),
                                    False, False, 0)
        self.listbox.show_all()
        self.empty.set_visible(not shown)
