#!/usr/bin/env python3
"""linux-island: "dynamic island" para Wayland (layer-shell) no lugar do relógio do painel.

Mostra hora, data, clima e o Spotify; expande ao passar o mouse.
"""
import ctypes
import os
import socket
import sys
import threading
from datetime import date, datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ValueError, ImportError):
    sys.exit("gtk-layer-shell não encontrado. Rode pelo run.sh ou instale "
             "gir1.2-gtklayershell-0.1")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

import anim  # noqa: E402
import kde  # noqa: E402
import palette  # noqa: E402
from autotheme import AutoTheme  # noqa: E402
from privacy import PrivacyWatcher  # noqa: E402
from focus import Focus, fmt as fmt_focus  # noqa: E402
from focus_view import FocusPage  # noqa: E402
from icons import Glyph  # noqa: E402
from logutil import warn  # noqa: E402
from bluetooth import Bluetooth  # noqa: E402
from bluetooth_view import BluetoothPage  # noqa: E402
from camera_view import CameraPage  # noqa: E402
from notif_history import NotificationHistory  # noqa: E402
from notifs_view import NotifsPage  # noqa: E402
from tasks import Tasks  # noqa: E402
from tasks_view import TasksPage  # noqa: E402
from notch import NotchMixin  # noqa: E402
from autohide import AutoHideMixin  # noqa: E402
from pages import PAGES, TRANSITION_MS, PagesMixin  # noqa: E402
from pointer import InputMixin, log  # noqa: E402
import i18n  # noqa: E402
from i18n import _  # noqa: E402
from config import Config, accent_tuple, build_css, rgba  # noqa: E402
from settings import Settings  # noqa: E402
from players import Players  # noqa: E402
from notifications import parse_ignore as parse_names  # noqa: E402
from spotify_web import SpotifyWeb  # noqa: E402
from notifications import NotificationWatcher  # noqa: E402
from views import Compact, Expanded, NotifPill, label  # noqa: E402
from water import Notifier, Water, play_sound  # noqa: E402
from water_view import DropIcon, WaterPage  # noqa: E402
from claude_hub import ClaudeHub  # noqa: E402
from claude_sessions import read_sessions  # noqa: E402
from notifications import Notification  # noqa: E402
from system_view import CpuSampler, SystemPage  # noqa: E402
import brands  # noqa: E402
from agenda import Agenda  # noqa: E402
from agenda_view import AgendaPage, MeetingPill  # noqa: E402
from weather import Weather  # noqa: E402
from widgets import accent_from_pixbuf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ID = "io.github.mrlazarias.LinuxIsland"
PEEK_MS = 4000         # quanto tempo a pílula mostra a faixa nova
FOCUS_ALERT_MS = 10000  # quanto tempo a pílula avisa o fim do foco
COST_EVERY_S = 60      # de quanto em quanto tempo o gasto do dia é relido


class Island(NotchMixin, AutoHideMixin, PagesMixin, InputMixin, Gtk.Window):
    def __init__(self, app, cfg):
        super().__init__(title="linux-island")
        self.app = app
        self.cfg = cfg
        anim.set_speed(cfg["animations"])
        palette.apply(cfg)
        self.notif_history = NotificationHistory(cfg["notif_history_max"])
        self.focus = Focus(cfg, self._on_focus_change, self._on_focus_done)
        self.tasks = Tasks()
        self.bluetooth = Bluetooth(self._on_bluetooth, self._on_bluetooth_error)
        self._editing, self._kbd_mode = False, None
        self._focus_shown = False
        self._cost_busy = False
        self._limit_day = None
        self._art_accent = None
        self._monitor, self._monitor_set = None, False
        self._setup_surface()
        self.expanded = False
        self.hovered = False
        self._timers = {}
        self._resize_tick = None
        self._last_click = None
        self._closed_by_click = False
        self._sync_counter = 0
        self._minute = None

        self.player = Players(self._on_presence, self._on_track, self._on_status,
                              self._on_art, self._on_volume, on_switch=self._on_player_switch,
                              ignored=self._player_ignored)
        self._last_scroll = None
        self._scroll_acc = 0.0
        self._last_discrete = None
        self._press = None
        self._hscroll = 0.0
        self.water = Water(cfg, self._on_water_change, self._on_water_alert)
        self.agenda = Agenda(cfg, self._on_agenda_change, self._on_agenda_alert,
                             self._on_agenda_status, play_sound)
        self._build()
        self.weather = Weather(self._on_weather, cfg["city"], cfg["units"])
        self.web_status = ("Conectado", True)
        self.web = SpotifyWeb(cfg["spotify_client_id"], self._on_playback, self._on_web_status)
        if not self.web.connected:
            self.web_status = (_("Não conectado"), False)
        self._notif_queue, self._notif_current = [], None
        self.notifications = NotificationWatcher(self._on_notification)
        self._apply()
        cfg.connect(self._apply)
        cfg.watch()
        self.show_all()
        self._notch_init()
        self._autohide_init()
        self.autotheme = AutoTheme(cfg, self._on_kde_change)
        self.autotheme.start()
        self.bluetooth.start()
        self.privacy = PrivacyWatcher(self._on_privacy)
        if cfg["privacy_indicator"]:
            self.privacy.start()
        GLib.timeout_add(250, self._tick_music)
        GLib.timeout_add(1000, self._tick_clock)
        self._cpu = CpuSampler()
        self._claude_state = None  # sid -> (status, desde); None até a primeira leitura
        GLib.timeout_add(2000, self._tick_claude)
        GLib.timeout_add(2000, self._tick_cpu)
        GLib.timeout_add_seconds(5, self._first_cost)
        GLib.timeout_add_seconds(COST_EVERY_S, self._tick_cost)

    # --- superfície layer-shell ----------------------------------------
    def _setup_surface(self):
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, "linux-island")
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, True)
        # -1: ignora a zona exclusiva do painel e fica por cima dele, no lugar do relógio
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)

        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.get_style_context().add_class("island-window")

        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(HERE, "style.css"))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # cores e cantos vindos da configuração, por cima do style.css
        self.dyn_css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.dyn_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

    # --- configuração ---------------------------------------------------
    def _apply(self, key=None):
        """Aplica a configuração inteira (key=None) ou só o que mudou."""
        cfg = self.cfg
        look = ("bg_color", "text_color", "border", "radius_expanded", "radius_compact",
                "animations", "color_water", "color_meeting", "color_focus", "color_claude")
        if key is None or key == "animations":
            anim.set_speed(cfg["animations"])
        if key is None or key.startswith("color_"):
            palette.apply(cfg)
            self.focus_page.update()   # o anel do foco usa a cor do tema
            self.water_page.update(cfg)
            self.claude_page.refresh_limit()
        if key is None or key in look:
            self.dyn_css.load_from_data(build_css(cfg).encode())
            self.queue_draw()
            fg = rgba(cfg["text_color"])
            bg = rgba(cfg["bg_color"])
            self.full.card_base = (bg.red, bg.green, bg.blue)
            self.full.music_box.queue_draw()
            self.focus_page.set_fg((fg.red, fg.green, fg.blue))
            self.system_page.set_fg((fg.red, fg.green, fg.blue))
            self.compact.cpu_ring.fg = self.compact.cup.fg = (fg.red, fg.green, fg.blue)
            self.compact.cup.queue_draw()
            self.compact.cpu_ring.queue_draw()
            for bar in (self.full.progress, self.full.vol_bar):
                bar.fg = (fg.red, fg.green, fg.blue)
                bar.queue_draw()
            self.water_page.set_fg((fg.red, fg.green, fg.blue))
            self.claude_page.set_fg((fg.red, fg.green, fg.blue))
        if key is None or key in ("accent_auto", "accent_color", "accent_follow_kde"):
            self._apply_accent()
        if key in ("theme_auto", "theme_light", "theme_dark", "theme_dark_from_h",
                   "theme_dark_to_h") and getattr(self, "autotheme", None):
            self.autotheme.evaluate(force=True)
        if key is None or key == "clock_24h":
            self._minute = None
            self._tick_clock()
        if key is None or key in ("show_date", "show_weather"):
            self.compact.set_visibility(cfg["show_date"], cfg["show_weather"])
        if key == "player_ignore":
            self.player.refresh_choice()
        if key in ("city", "units"):
            self.weather.configure(cfg["city"], cfg["units"])
        if key == "spotify_client_id":
            self.web.set_client_id(cfg["spotify_client_id"])
        if key is None or (key or "").startswith("agenda_"):
            if key in ("agenda_enabled", "agenda_days"):
                self.agenda.refresh()
            if key == "agenda_write":
                self.agenda.apply_write_setting()
            self.agenda.tick()
            self._on_agenda_change()
        if key is None or (key or "").startswith("water_"):
            self.water.tick()
            self._on_water_change()
        if key is None or key == "keep_awake":
            self.system_page.sync_awake()
        if key is None or key == "show_cpu":
            self.compact.cpu_rev.set_reveal_child(cfg["show_cpu"])
        if key == "privacy_indicator" and getattr(self, "privacy", None):
            self.privacy.start() if cfg[key] else self.privacy.stop()
        if key is None or key == "eq_style":
            for eq in (self.compact.eq, self.full.eq):
                eq.set_style(cfg["eq_style"])
        if key is None or key == "art_glow":
            self._apply_accent()
        if key is None or key in ("pages_order", "pages_hidden"):
            self._apply_pages()
        if key == "notif_history_max":
            self.notif_history.set_max(cfg["notif_history_max"])
        if key == "notif_history" and not cfg["notif_history"]:
            self.notif_history.clear()  # desligou o histórico: apaga o que já havia
        if key is None or (key or "").startswith("pomo_"):
            self.focus.config_changed()
        if key is None or key in ("claude_pill_cost", "claude_daily_limit"):
            if not cfg["claude_pill_cost"]:
                self.compact.set_cost(None)
            if key is not None:
                self._tick_cost()
            if key == "claude_daily_limit":
                self.claude_page.refresh_limit()
        if key is None or key == "monitor":
            self._place_on_monitor()
        if key is None or key in ("notch_style", "glass_style", "notch_ear", "radius_compact"):
            self._notch_apply()
        if key is None or key in ("margin_top", "notch_style", "glass_style"):
            if not getattr(self, "_hidden", False):
                GtkLayerShell.set_margin(self, GtkLayerShell.Edge.TOP, self._top_margin())
                self._margin_now = float(self._top_margin())
        self._follow_size()

    def _place_on_monitor(self):
        """Move a ilha para o monitor escolhido (0 = o compositor decide)."""
        display = Gdk.Display.get_default()
        n = int(self.cfg["monitor"])
        mon = display.get_monitor(n - 1) if 1 <= n <= display.get_n_monitors() else None
        if mon is self._monitor and self._monitor_set:
            return
        if mon is None and not self._monitor_set:
            return  # automático desde o início: deixa o compositor escolher
        self._monitor, self._monitor_set = mon, True
        # set_monitor não aceita None: "automático" depois de ter escolhido vira o monitor 1
        # com a janela aberta o próprio gtk-layer-shell recria a superfície na nova saída;
        # um hide()/show() nosso por cima remapeava duas vezes e corria contra o desfoque
        if mon is not None:
            GtkLayerShell.set_monitor(self, mon)
        else:  # "automático" de verdade: o PyGObject não aceita None, a biblioteca C aceita NULL
            try:
                lib = ctypes.CDLL("libgtk-layer-shell.so.0")
                lib.gtk_layer_shell_set_monitor.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                lib.gtk_layer_shell_set_monitor(hash(self), None)
            except (OSError, AttributeError):
                GtkLayerShell.set_monitor(self, display.get_monitor(0))

    def _apply_accent(self):
        kde_accent = kde.accent() if self.cfg["accent_follow_kde"] else None
        if kde_accent:
            accent = kde_accent
        elif self.cfg["accent_auto"] and self._art_accent:
            accent = self._art_accent
        elif self.cfg["accent_auto"]:
            accent = accent_from_pixbuf(None)
        else:
            accent = accent_tuple(self.cfg["accent_color"])
        for w in (self.compact.eq, self.full.eq, self.full.progress, self.full.vol_bar):
            w.accent = accent
            w.queue_draw()
        self.full.set_art_mode(self.cfg["art_glow"], accent)
        self.system_page.set_accent(accent)
        self.tasks_page.set_accent(accent)
        self.tasks_page.update()

    # --- layout ---------------------------------------------------------
    def _build(self):
        # Eventos na própria janela: o Gtk.Stack tem GdkWindow própria, então
        # cliques sobem direto para a janela e um EventBox no meio não os vê.
        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
                        | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.connect("button-release-event", self._release)
        self.connect("scroll-event", self._scroll)
        self.connect("enter-notify-event", self._enter)
        self.connect("leave-notify-event", self._leave)
        self.connect("button-press-event", self._click)

        # Sem margem transparente em volta: no Wayland/GTK3 a região de input
        # não funciona aqui, e qualquer área transparente bloquearia cliques.
        self.shell = Gtk.Box()
        self.shell.get_style_context().add_class("island")
        self.add(self.shell)

        self.stack = Gtk.Stack()
        self.stack.set_homogeneous(False)
        self.stack.set_interpolate_size(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        anim.register(self.stack, TRANSITION_MS)
        self.shell.pack_start(self.stack, True, True, 0)

        self.compact = Compact()
        self.full = Expanded(self.player)
        self.water_page = WaterPage(self.water)
        self.agenda_page = AgendaPage(self.agenda, lambda: self.app.open_settings("agenda"))
        self.system_page = SystemPage(self.cfg, lambda on: self.compact.set_awake(on))
        self.claude_hub = ClaudeHub(self.cfg)  # sessões, agentes e uso numa página só
        self.claude_page = self.claude_hub.usage
        self.notifs_page = NotifsPage(self.notif_history)
        self.focus_page = FocusPage(self.focus)
        self.tasks_page = TasksPage(self.tasks, self._on_editing)
        self.camera_page = CameraPage()
        self.bluetooth_page = BluetoothPage(self.bluetooth)
        self.notif_history.connect(self._update_badges)
        self.stack.add_named(self.compact, "compact")
        self.stack.add_named(self._build_pages(), "expanded")
        self.stack.set_visible_child_name("compact")

        # alerta de água no miolo da pílula
        alert = Gtk.Box(spacing=8)
        alert.pack_start(DropIcon(15), False, False, 0)
        msg = label("clock")
        msg.set_text(_("Hora de beber água"))
        self.alert_amount = label("dim")
        alert.pack_start(msg, False, False, 0)
        alert.pack_start(self.alert_amount, False, False, 0)
        self.compact.middle.add_named(alert, "water")
        self.meeting_pill = MeetingPill()
        self.compact.middle.add_named(self.meeting_pill, "meeting")
        self.notif_pill = NotifPill()
        self.compact.middle.add_named(self.notif_pill, "notif")
        focus_alert = Gtk.Box(spacing=8)
        focus_alert.pack_start(Glyph("timer", 15), False, False, 0)
        self.focus_msg = label("clock")
        focus_alert.pack_start(self.focus_msg, False, False, 0)
        self.compact.middle.add_named(focus_alert, "focus")

    # --- tamanho --------------------------------------------------------
    def _follow_size(self):
        """Janelas GTK3 não encolhem sozinhas: acompanha as animações de tamanho."""
        if self._resize_tick is not None:
            self.remove_tick_callback(self._resize_tick)
        start = GLib.get_monotonic_time()

        def step(_w, _clock):
            self.resize(1, 1)
            if GLib.get_monotonic_time() - start > (anim.ms(TRANSITION_MS) + 120) * 1000:
                self._resize_tick = None
                return False
            return True

        self._resize_tick = self.add_tick_callback(step)

    def set_expanded(self, value):
        if value == self.expanded:
            return
        self.expanded = value
        log("expanded", value)
        ctx = self.shell.get_style_context()
        (ctx.add_class if value else ctx.remove_class)("expanded")
        self.stack.set_visible_child_name("expanded" if value else "compact")
        if not value:
            self.camera_page.stop_all()   # fechar a ilha desliga o teste de câmera e microfone
        self._update_keyboard()
        if value:  # ao expandir, a pílula volta ao relógio para quando fechar
            self._cancel("track_peek")
            self._cancel("notif_peek")
            self._notif_queue, self._notif_current = [], None
            self._refresh_middle()
            if self._alert_page() != "home":
                self.set_page(self._alert_page())
        else:
            self.set_page(self._alert_page())
        self._follow_size()
        if value:
            self._tick_music()

    def _peek(self):
        """Faixa nova: a pílula se estica na horizontal com título · artista e volta."""
        if self.expanded or not self.cfg["peek_on_track"]:
            return
        self._later("track_peek", PEEK_MS, self._refresh_middle)
        self._refresh_middle()

    # --- relógio e clima ------------------------------------------------
    def _tick_claude(self):
        """Avisa na pílula quando uma sessão do Claude Code termina e passa a esperar você."""
        if not self.cfg["claude_alert"]:
            self._claude_state = None  # ao religar, a primeira leitura é só o ponto de partida
            return True
        try:
            sessions = read_sessions()
        except Exception as e:  # nunca atrapalha a ilha, mas fica registrado
            warn("não deu para ler as sessões do Claude Code", e)
            return True
        now = {s["sid"]: s for s in sessions}
        prev = self._claude_state
        self._claude_state = {sid: (s["status"], s["since"]) for sid, s in now.items()}
        if prev is None:
            return True
        for sid, s in now.items():
            was = prev.get(sid)
            if was and was[0] == "busy" and s["status"] == "idle" and s["since"] - was[1] >= 5:
                self._on_notification(Notification(
                    "Claude Code", s["project"], _("terminou · aguardando você"), None, ""))
            elif (was and self.cfg["claude_attention"] and was[0] != s["status"]
                  and s["status"] not in ("busy", "idle", "?")):
                # qualquer outro estado que o Claude Code informe (ex.: pedindo permissão)
                self._on_notification(Notification(
                    "Claude Code", s["project"], _("precisa de você"), None, ""))
        return True

    def _first_cost(self):
        self._tick_cost()
        return False

    def _tick_cost(self):
        """Gasto do dia no Claude Code ao lado do relógio (relê o histórico fora da UI)."""
        if not (self.cfg["claude_pill_cost"] or self.cfg["claude_daily_limit"]) or self._cost_busy:
            return True
        self._cost_busy = True
        store = self.claude_page.store

        def work():
            cost = None
            try:
                store.refresh()
                cost = store.summary(1)["cost"]
            except Exception as e:  # leitura do histórico nunca derruba a ilha
                warn("gasto do dia no Claude Code", e)
            GLib.idle_add(self._cost_done, cost)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _cost_done(self, cost):
        self._cost_busy = False
        limit = self.cfg["claude_daily_limit"]
        over = bool(limit) and cost is not None and cost >= limit
        shown = self.cfg["claude_pill_cost"] and cost is not None and cost >= 0.01
        self.compact.set_cost(f"US$ {cost:.2f}" if shown else None, over)
        if over and self._limit_day != date.today():
            self._limit_day = date.today()  # avisa uma vez por dia
            self._on_notification(Notification(
                "Claude Code", _("Limite diário atingido"),
                _("US$ {c:.2f} de US$ {l} hoje").format(c=cost, l=limit), None, ""))
        self._follow_size()
        return False

    def _on_bluetooth(self):
        """Adaptador apareceu/sumiu ou a lista mudou: a página entra e sai dos pontinhos."""
        was = self.dots["bluetooth"].get_visible()
        self.bluetooth_page.update()
        if was != (self.bluetooth.available and "bluetooth" in self._page_names()):
            self._apply_pages()
        self._follow_size()

    def _on_bluetooth_error(self, text):
        self.bluetooth_page.show_error(text)

    def _on_privacy(self, state):
        """Câmera ou microfone começou/parou de ser usado: atualiza os ícones da pílula."""
        log("privacidade", state)
        self.compact.set_privacy(state["mic"], state["cam"])
        if state["mic"] or state["cam"]:
            self.autohide_poke()   # o ícone aparece mesmo com a ilha escondida no topo
        self._follow_size()

    def _on_kde_change(self):
        """O KDE mudou de tema ou de cor de destaque: refaz o destaque e o visual das configurações."""
        if self.cfg["accent_follow_kde"]:
            self._apply_accent()
        if self.app.settings:
            self.app.settings._restyle()

    # --- foco / pomodoro ------------------------------------------------------
    def _on_focus_change(self):
        f = self.focus
        shown = f.active
        self.compact.set_focus_timer(fmt_focus(f.remaining) if shown else None)
        if self.expanded or self.focus_page.get_mapped():
            self.focus_page.update()
        if shown != self._focus_shown:  # só muda o tamanho quando o contador entra ou sai
            self._focus_shown = shown
            self._follow_size()

    def _on_focus_done(self, finished, nxt):
        log("focus done", finished, nxt)
        if self.cfg["pomo_sound"]:
            play_sound("complete", self.cfg["water_sound_volume"])
        self.focus_msg.set_text({"focus": _("Foco concluído · hora da pausa"),
                                 "short": _("Pausa acabou · hora de focar"),
                                 "long": _("Pausa acabou · hora de focar"),
                                 "timer": _("Timer terminou")}.get(finished, _("Terminou")))
        ctx = self.shell.get_style_context()
        ctx.add_class("focus-alert")

        def end():
            self.shell.get_style_context().remove_class("focus-alert")
            self._refresh_middle()

        self._later("focus_alert", FOCUS_ALERT_MS, end)
        self._refresh_middle()

    # --- teclado (página Tarefas) ---------------------------------------------
    def _on_editing(self, editing):
        self._editing = editing

    def _update_keyboard(self):
        """O teclado só chega à ilha na página Tarefas (para digitar); no resto fica de fora."""
        want = self.expanded and self.pages.get_visible_child_name() == "tasks"
        mode = (GtkLayerShell.KeyboardMode.ON_DEMAND if want
                else GtkLayerShell.KeyboardMode.NONE)
        if mode != self._kbd_mode:
            self._kbd_mode = mode
            GtkLayerShell.set_keyboard_mode(self, mode)

    def flash(self, summary, body=""):
        """Mensagem curta na pílula (ex.: confirmação de um comando de atalho)."""
        if self.expanded:
            return
        n = Notification("linux-island", summary, body, None, "")
        self._notif_queue = (self._notif_queue + [n])[-5:]
        if "notif_peek" not in self._timers:
            self._show_next_notification()

    def _tick_cpu(self):
        if self.cfg["show_cpu"] and not self.expanded:
            self.compact.set_cpu(self._cpu.usage())
        return True

    def _tick_clock(self):
        self.focus.tick()
        now = datetime.now()
        if now.minute != self._minute:
            self._minute = now.minute
            if self.cfg["theme_auto"] == "schedule":
                self.autotheme.evaluate(now=now)   # só troca quando o período muda
            self.compact.set_clock(now, self.cfg["clock_24h"])
            self.full.set_clock(now, self.cfg["clock_24h"])
            if self.agenda.alert:  # atualiza a contagem regressiva da reunião
                self._refresh_middle()
            self._on_agenda_change()
            self._follow_size()
        return True

    def _on_weather(self, fc):
        self.compact.set_weather(fc)
        self.full.set_weather(fc)
        self._follow_size()

    # --- Spotify --------------------------------------------------------
    def _on_presence(self, present):
        if not present:
            self._on_track(None)
            self._on_status(False)

    def _on_track(self, track):
        prev = self.full.title.get_text() if self.full.music_rev.get_reveal_child() else ""
        self.full.set_track(track)
        self._show_art()
        if track:
            self.compact.set_track_text(track.title, track.artist)
        self.compact.set_music(track is not None, self.player.playing)
        self._follow_size()
        self.web.kick()
        if track and prev and prev != track.title:
            self._peek()

    def _on_status(self, playing):
        self.compact.set_music(self.player.track is not None, playing)
        self.full.set_playing(playing)
        self._follow_size()
        self.web.kick()

    # --- Spotify Web API (playlist e dispositivo) -----------------------
    def _player_ignored(self, p):
        """Players que o usuário pediu para ignorar (ex.: navegadores)."""
        names = parse_names(self.cfg["player_ignore"])
        ident = (p.identity or "").lower()
        return any(n == p.short or n in ident for n in names)

    def _on_player_switch(self, p):
        log("player ativo", p and p.identity)
        if p is None or not p.is_spotify:
            # playlist e dispositivo só fazem sentido para o Spotify
            self.full.set_playback(None)
            self.compact.set_remote_device(None)
        else:
            self.web.kick()
        self._follow_size()

    def _on_playback(self, pb):
        if not self.player.is_spotify:
            pb = None
        self.full.set_playback(pb)
        remote = pb is not None and pb.is_playing and not self._is_this_computer(pb)
        self.compact.set_remote_device(pb.device_icon if remote else None)
        self._follow_size()

    @staticmethod
    def _is_this_computer(pb):
        # o app de desktop se registra com o hostname como nome do dispositivo
        return pb.device_type == "computer" and pb.device.lower() == socket.gethostname().lower()

    def _on_web_status(self, text, ok):
        self.web_status = (text, ok)
        if self.app.settings:
            self.app.settings.set_spotify_status(text, ok)

    def _on_art(self, path):
        pb = None
        if path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(path)
            except GLib.Error as e:
                print(f"[island] capa inválida: {e.message}")
        self._art_pixbuf = pb
        self._show_art()

    def _show_art(self):
        """Capa do que toca. Serviços conhecidos (YouTube, WhatsApp...) viram a logo, sempre a
        mesma; senão vale a capa do player (álbum) ou o círculo padrão."""
        t = self.player.track
        brand = brands.detect(t.title, t.url) if t else None
        cover = getattr(self, "_art_pixbuf", None)
        if brand in brands.MUSIC and cover:
            brand = None  # música: a capa do álbum vale mais que a logo
        pb = None if brand else cover
        for art in (self.compact.art, self.full.art):
            art.set_brand(brand)
            art.set_source(pb)
        self.full.set_art_pixbuf(pb)
        if brand:
            self._art_accent = brands.COLORS[brand]
        else:
            self._art_accent = accent_from_pixbuf(pb) if pb else None
        self._apply_accent()

    def _tick_music(self):
        p = self.player
        if p.track:
            if p.playing:
                self._sync_counter += 1
                if self._sync_counter % 12 == 0:  # ressincroniza a cada ~3s
                    p.sync_position()
            if self.expanded:
                self.full.set_position(p.position(), p.track.length)
        return True


class App(Gtk.Application):
    """Instância única: rodar de novo (ex.: --settings) fala com a que já existe."""

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.island = None
        self.settings = None
        self.add_main_option("settings", ord("s"), GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE, _("Abre as configurações"), None)
        self.add_main_option("toggle", ord("t"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Expande ou recolhe a ilha (para atalho de teclado)"), None)
        # token de ativação do Wayland (o main() o copia de XDG_ACTIVATION_TOKEN): sem ele o
        # KWin deixa a janela de configurações atrás das outras quando aberta por atalho
        self.add_main_option("activation-token", 0, GLib.OptionFlags.HIDDEN,
                             GLib.OptionArg.STRING, "", "TOKEN")
        self.add_main_option("page", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             _("Expande a ilha já numa página: ") + ", ".join(PAGES), "PÁGINA")
        for name, text in (("next-page", "Próxima página (abre a ilha se estiver fechada)"),
                           ("prev-page", "Página anterior (abre a ilha se estiver fechada)"),
                           ("play-pause", "Toca ou pausa a música"),
                           ("next-track", "Próxima faixa"),
                           ("prev-track", "Faixa anterior"),
                           ("dnd", "Liga ou desliga o não perturbe das notificações"),
                           ("focus", "Inicia ou pausa o foco (pomodoro)")):
            self.add_main_option(name, 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, _(text), None)
        self.add_main_option("city", 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
                             _("Cidade do clima só nesta execução"), "CIDADE")
        self.add_main_option("margin", 0, GLib.OptionFlags.NONE, GLib.OptionArg.INT,
                             _("Distância do topo só nesta execução"), "PX")
        self.notifier = Notifier(self._notif_action)

    def notify_water(self, consumed, goal):
        self.notifier.notify(consumed, goal)

    def withdraw_water(self):
        self.notifier.close()

    def _notif_action(self, action):
        if self.island is None:
            return
        if action == "drink":
            self.island.water.drink()
        elif action == "snooze":
            self.island.water.snooze()

    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        log("command line", opts, "remota" if cmdline.get_is_remote() else "local")
        if self.island is None:
            margin = opts.get("margin")
            cfg = Config({"city": opts.get("city"),
                          "margin_top": margin if margin is not None and 0 <= margin <= 200
                          else None})
            self.island = Island(self, cfg)
            self.add_window(self.island)
        isl = self.island
        if opts.get("page") in PAGES:
            isl.autohide_poke()
            isl.set_expanded(True)
            isl.set_page(opts["page"], forced=True)
        elif opts.get("next-page") or opts.get("prev-page"):
            isl.autohide_poke()
            if not isl.expanded:
                isl.set_expanded(True)  # a primeira chamada só abre; as seguintes viram a página
            else:
                isl.turn_page(1 if opts.get("next-page") else -1)
        elif opts.get("toggle"):
            isl.autohide_poke()
            isl.set_expanded(not isl.expanded)
        if opts.get("play-pause"):
            isl.player.play_pause()
        if opts.get("next-track"):
            isl.player.next()
        if opts.get("prev-track"):
            isl.player.previous()
        if opts.get("dnd"):
            on = not isl.cfg["notif_dnd"]
            isl.cfg.set("notif_dnd", on)
            isl.autohide_poke()
            isl.flash(_("Não perturbe: ligado") if on else _("Não perturbe: desligado"))
        if opts.get("focus"):
            isl.focus.toggle()
            isl.autohide_poke()
            isl.flash(_("Foco em andamento") if isl.focus.running else _("Foco pausado"),
                      fmt_focus(isl.focus.remaining))
        if opts.get("settings"):
            self.open_settings(token=opts.get("activation-token"))
        return 0

    def restart(self):
        """Reabre a ilha (ex.: para trocar o idioma). O ambiente do run.sh é herdado."""
        log("reiniciando")
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable, os.path.join(HERE, "island.py")])

    def open_settings(self, page=None, token=None):
        log("open_settings", self.settings)
        if self.settings is None:
            isl = self.island
            self.settings = Settings(isl.cfg, self, isl.web, isl.water, isl.agenda)
            self.settings.set_spotify_status(*isl.web_status)
            self.settings.set_agenda_status(*isl.agenda.status)
            self.settings.connect("destroy", lambda *_a: setattr(self, "settings", None))
        if page:
            self.settings.show_page(page)
        if token:  # xdg-activation: deixa o KWin trazer a janela para a frente
            try:
                Gdk.Display.get_default().set_startup_notification_id(token)
            except (AttributeError, TypeError):
                pass
        self.settings.present()


def main():
    # o idioma vale para tudo, até as ajudas da linha de comando: escolhe antes de criar a UI
    i18n.setup(Config()["language"])
    app = App()
    tok = os.environ.get("XDG_ACTIVATION_TOKEN")
    if tok and not any(a.startswith("--activation-token") for a in sys.argv):
        sys.argv.append(f"--activation-token={tok}")
    try:  # GLib.unix_signal_add é obsoleta nas versões novas do PyGObject
        from gi.repository import GLibUnix
        add_signal = lambda sig, fn: GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig, fn)  # noqa: E731
    except ImportError:
        add_signal = lambda sig, fn: GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, fn)  # noqa: E731
    for sig in (2, 15):  # SIGINT, SIGTERM
        add_signal(sig, lambda: app.quit() or False)
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
