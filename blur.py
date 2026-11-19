"""Desfoque do fundo no Wayland, pelo protocolo ext-background-effect-v1 (KWin 6.8+).

O GTK3 não sabe pedir isso, então falamos o protocolo direto com a libwayland-client via
ctypes: acha o gerenciador no registro, pede um "background effect" para a superfície da
janela e diz a região a desfocar (a forma da ilha). Quem desfoca é o compositor. Se algo
faltar (outro compositor, efeito desligado), `Blur.available` fica falso e nada acontece.
O pedido vale no próximo commit da superfície, que o GTK faz ao redesenhar.
"""
import ctypes as C
import math
from ctypes import CFUNCTYPE, POINTER, Structure, c_char_p, c_int, c_uint32, c_void_p

try:
    _wl = C.CDLL("libwayland-client.so.0")
    _gdk = C.CDLL("libgdk-3.so.0")
except OSError:
    _wl = _gdk = None


class _Msg(Structure):
    _fields_ = [("name", c_char_p), ("signature", c_char_p), ("types", POINTER(c_void_p))]


class _Iface(Structure):
    _fields_ = [("name", c_char_p), ("version", c_int), ("method_count", c_int),
                ("methods", POINTER(_Msg)), ("event_count", c_int), ("events", POINTER(_Msg))]


def _sym(name):
    return C.addressof(_Iface.in_dll(_wl, name))


def _types(*ptrs):
    return (c_void_p * max(1, len(ptrs)))(*ptrs)


if _wl:
    _wl.wl_proxy_marshal_flags.restype = c_void_p
    _wl.wl_proxy_marshal_flags.argtypes = [c_void_p, c_uint32, c_void_p, c_uint32, c_uint32]
    _wl.wl_proxy_get_version.restype = c_uint32
    _wl.wl_proxy_get_version.argtypes = [c_void_p]
    _wl.wl_proxy_add_listener.argtypes = [c_void_p, c_void_p, c_void_p]
    _wl.wl_display_roundtrip.argtypes = [c_void_p]
    _wl.wl_display_flush.argtypes = [c_void_p]
    _gdk.gdk_wayland_display_get_wl_display.restype = c_void_p
    _gdk.gdk_wayland_display_get_wl_display.argtypes = [c_void_p]
    _gdk.gdk_wayland_window_get_wl_surface.restype = c_void_p
    _gdk.gdk_wayland_window_get_wl_surface.argtypes = [c_void_p]

    _SURFACE, _REGION = _sym("wl_surface_interface"), _sym("wl_region_interface")
    _FX_MSGS = (_Msg * 2)(
        _Msg(b"destroy", b"", _types()),
        _Msg(b"set_blur_region", b"?o", _types(_REGION)))
    _FX = _Iface(b"ext_background_effect_surface_v1", 1, 2, _FX_MSGS, 0, None)
    _MGR_MSGS = (_Msg * 2)(
        _Msg(b"destroy", b"", _types()),
        _Msg(b"get_background_effect", b"no", _types(C.addressof(_FX), _SURFACE)))
    _MGR_EVENTS = (_Msg * 1)(_Msg(b"capabilities", b"u", _types(None)))
    _MGR = _Iface(b"ext_background_effect_manager_v1", 1, 2, _MGR_MSGS, 1, _MGR_EVENTS)

_GLOBAL = CFUNCTYPE(None, c_void_p, c_void_p, c_uint32, c_char_p, c_uint32)
_REMOVE = CFUNCTYPE(None, c_void_p, c_void_p, c_uint32)


def _call(proxy, opcode, iface, *args, flags=0):
    """Chama wl_proxy_marshal_flags com a versão do próprio proxy."""
    ver = _wl.wl_proxy_get_version(proxy)
    fn = _wl.wl_proxy_marshal_flags
    return fn(proxy, opcode, iface, ver, flags, *args)


def shape_rows(w, h, radius, ear=0):
    """Linhas (y, x0, x1) cobrindo a forma da ilha (cantos de baixo redondos e, no
    entalhe, as orelhas côncavas de cima), em px da janela. Linhas iguais são fundidas."""
    left, right = ear, w - ear
    r = max(0.0, min(radius, h - ear, (right - left) / 2))
    rows = []
    for y in range(h):
        x0, x1 = left, right
        if y < ear:  # orelha côncava
            dx = math.sqrt(max(0.0, ear * ear - (ear - y - 0.5) ** 2))
            x0, x1 = left - (ear - dx), right + (ear - dx)
        if y > h - r:  # canto de baixo
            dy = y + 0.5 - (h - r)
            inset = r - math.sqrt(max(0.0, r * r - dy * dy))
            x0, x1 = x0 + inset, x1 - inset
        x0, x1 = int(math.floor(x0)), int(math.ceil(x1))
        if rows and rows[-1][3] == (x0, x1) and rows[-1][0] + rows[-1][1] == y:
            rows[-1][1] += 1
        else:
            rows.append([y, 1, 0, (x0, x1)])
    return [(y, n, x0, x1 - x0) for y, n, _p, (x0, x1) in rows]


class Blur:
    def __init__(self):
        self.available = False
        self._blur = None
        self._surface = None
        self._last = None
        self._keep = []
        self._disp = self._mgr = self._comp = None

    def attach(self, gdk_display, gdk_window):
        """Liga ao Wayland da janela. Devolve True se o KWin oferece o desfoque."""
        if _wl is None or gdk_window is None:
            return False
        try:
            self._disp = _gdk.gdk_wayland_display_get_wl_display(hash(gdk_display))
            self._surface = _gdk.gdk_wayland_window_get_wl_surface(hash(gdk_window))
        except (AttributeError, OSError):
            return False
        if not self._disp or not self._surface:
            return False
        found = {}

        def on_global(_d, registry, name, iface, version):
            if iface in (b"ext_background_effect_manager_v1", b"wl_compositor"):
                found[iface] = (registry, name, version)

        cb, rm = _GLOBAL(on_global), _REMOVE(lambda *_a: None)
        listener = (c_void_p * 2)(C.cast(cb, c_void_p), C.cast(rm, c_void_p))
        self._keep += [cb, rm, listener]
        registry = _call(self._disp, 1, _sym("wl_registry_interface"), None)  # get_registry
        _wl.wl_proxy_add_listener(registry, C.addressof(listener), None)
        _wl.wl_display_roundtrip(self._disp)
        if b"ext_background_effect_manager_v1" not in found or b"wl_compositor" not in found:
            return False

        def bind(iface_name, iface_ptr):
            _reg, name, _v = found[iface_name]
            return _wl.wl_proxy_marshal_flags(
                registry, 0, iface_ptr, 1, 0, c_uint32(name), iface_name, c_uint32(1), None)

        self._mgr = bind(b"ext_background_effect_manager_v1", C.addressof(_MGR))
        self._comp = bind(b"wl_compositor", _sym("wl_compositor_interface"))
        self.available = bool(self._mgr and self._comp)
        return self.available

    def set_shape(self, w, h, radius, ear=0):
        """Desfoca só a forma da ilha. Chamar de novo quando o tamanho mudar."""
        if not self.available or w <= 0 or h <= 0:
            return
        key = (w, h, round(radius), ear)
        if key == self._last:
            return
        self._last = key
        if self._blur is None:  # get_background_effect(new_id, surface)
            self._blur = _call(self._mgr, 1, C.addressof(_FX), None, c_void_p(self._surface))
        region = c_void_p(_call(self._comp, 1, _REGION, None))  # create_region (opcode 1; o 0 é create_surface)
        for y, n, x, width in shape_rows(w, h, radius, ear):
            _call(region.value, 1, None, c_int(x), c_int(y), c_int(width), c_int(n))  # add
        _call(self._blur, 1, None, region)  # set_blur_region (c_void_p: 64 bits no variádico)
        _call(region.value, 0, None, flags=1)  # destroy
        _wl.wl_display_flush(self._disp)

    def clear(self):
        if not self.available or self._blur is None:
            return
        _call(self._blur, 0, None, flags=1)  # destroy: tira o efeito no próximo commit
        self._blur, self._last = None, None
        _wl.wl_display_flush(self._disp)
