"""Bluetooth pelo BlueZ (D-Bus do sistema): dispositivos pareados, bateria e conectar/desconectar.

`parse_objects` é uma função pura (testável sem hardware). A classe `Bluetooth` só fala com o
BlueZ quando ele está no barramento (não o inicia à força): sem adaptador, `available` fica
False e a página some dos pontinhos da ilha.
"""
from gi.repository import Gio, GLib

from logutil import warn

BUS = "org.bluez"
ADAPTER, DEVICE, BATTERY = "org.bluez.Adapter1", "org.bluez.Device1", "org.bluez.Battery1"
REFRESH_DELAY_MS = 300


def parse_objects(objs):
    """Resposta do GetManagedObjects -> {"adapter": {...} | None, "devices": [...]}.

    Só entram dispositivos pareados ou conectados (os "visíveis ao redor" ficam de fora).
    Conectados primeiro, depois por nome."""
    adapter, devices = None, []
    for path, ifaces in (objs or {}).items():
        if ADAPTER in ifaces and adapter is None:
            p = ifaces[ADAPTER]
            adapter = {"path": path, "powered": bool(p.get("Powered")),
                       "name": p.get("Alias") or p.get("Name") or "Bluetooth"}
        if DEVICE in ifaces:
            p = ifaces[DEVICE]
            if not (p.get("Paired") or p.get("Connected")):
                continue
            battery = (ifaces.get(BATTERY) or {}).get("Percentage")
            devices.append({
                "path": path,
                "name": p.get("Alias") or p.get("Name") or p.get("Address") or "?",
                "icon": p.get("Icon") or "bluetooth",
                "connected": bool(p.get("Connected")),
                "battery": int(battery) if battery is not None else None})
    devices.sort(key=lambda d: (not d["connected"], d["name"].lower()))
    return {"adapter": adapter, "devices": devices}


class Bluetooth:
    def __init__(self, on_change, on_error=lambda text: None):
        self.on_change, self.on_error = on_change, on_error
        self.adapter, self.devices = None, []
        self.busy = set()            # dispositivos com Conectar/Desconectar em andamento
        self._conn = None
        self._watch = None
        self._sub = None
        self._refresh_id = None

    @property
    def available(self):
        return self.adapter is not None

    def start(self):
        Gio.bus_get(Gio.BusType.SYSTEM, None, self._got_bus)

    def _got_bus(self, _src, res):
        try:
            self._conn = Gio.bus_get_finish(res)
        except GLib.Error as e:
            warn("Bluetooth: sem acesso ao barramento do sistema", e)
            return
        # só observa o nome: não ativa o serviço se o PC não tem Bluetooth
        self._watch = Gio.bus_watch_name_on_connection(
            self._conn, BUS, Gio.BusNameWatcherFlags.NONE, self._appeared, self._vanished)

    def _appeared(self, _conn, _name, _owner):
        if self._sub is None:
            self._sub = self._conn.signal_subscribe(
                BUS, None, None, None, None, Gio.DBusSignalFlags.NONE,
                lambda *_a: self._schedule_refresh())
        self.refresh()

    def _vanished(self, _conn, _name):
        self.adapter, self.devices = None, []
        self.busy.clear()
        self.on_change()

    def _schedule_refresh(self):
        if self._refresh_id is None:
            self._refresh_id = GLib.timeout_add(REFRESH_DELAY_MS, self._refresh_now)

    def _refresh_now(self):
        self._refresh_id = None
        self.refresh()
        return False

    def refresh(self):
        if self._conn is None:
            return
        self._conn.call(BUS, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                        None, GLib.VariantType("(a{oa{sa{sv}}})"), Gio.DBusCallFlags.NONE,
                        3000, None, self._got_objects)

    def _got_objects(self, conn, res):
        try:
            objs = conn.call_finish(res).unpack()[0]
        except GLib.Error as e:
            warn("Bluetooth: não deu para listar os dispositivos", e)
            return
        parsed = parse_objects(objs)
        self.adapter, self.devices = parsed["adapter"], parsed["devices"]
        self.on_change()

    # --- ações ---------------------------------------------------------------------
    def _call(self, path, iface, method, params, reply, timeout_ms, done):
        self._conn.call(BUS, path, iface, method, params, reply, Gio.DBusCallFlags.NONE,
                        timeout_ms, None, done)

    def toggle_device(self, device):
        """Conecta se estiver desconectado, e vice-versa. O resultado volta por refresh()."""
        if self._conn is None or device["path"] in self.busy:
            return
        path = device["path"]
        method = "Disconnect" if device["connected"] else "Connect"
        self.busy.add(path)
        self.on_change()

        def done(conn, res):
            self.busy.discard(path)
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                warn(f"Bluetooth: {method} falhou", e)
                self.on_error(e.message)
            self.refresh()

        self._call(path, DEVICE, method, None, None, 25000, done)

    def set_powered(self, on):
        if self._conn is None or self.adapter is None:
            return

        def done(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                warn("Bluetooth: não deu para ligar/desligar o adaptador", e)
                self.on_error(e.message)
            self.refresh()

        self._call(self.adapter["path"], "org.freedesktop.DBus.Properties", "Set",
                   GLib.Variant("(ssv)", (ADAPTER, "Powered", GLib.Variant("b", bool(on)))),
                   None, 5000, done)
