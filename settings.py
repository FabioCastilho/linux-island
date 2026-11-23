"""Janela de configurações. Tudo é aplicado ao vivo e salvo automaticamente."""
import os

from gi.repository import Gdk, GLib, Gtk

import kde
from config import css_color, rgba
from i18n import LANGUAGES, _
from icons import glyph_button
from settings_pages import SettingsPagesMixin
from settings_themes import SettingsThemesMixin
from themes import THEME_KEYS

AUTOSTART = os.path.join(GLib.get_user_config_dir(), "autostart", "linux-island.desktop")
RUN_SH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.sh")

def settings_css(cfg):
    """Mesmo visual da ilha: fundo/texto da config, cantos redondos, pílulas."""
    bg, fg = rgba(cfg["bg_color"]), rgba(cfg["text_color"])
    bg.alpha = 1.0  # a janela de configurações não fica transparente
    follow = kde.accent_spec() if cfg["accent_follow_kde"] else None
    ac = rgba(follow or ("rgb(30,215,96)" if cfg["accent_auto"] else cfg["accent_color"]))
    B, F, A = css_color(bg), css_color(fg), css_color(ac)

    def f(a):
        return css_color(fg, a)

    return f"""
window.island-settings, window.island-settings.background {{
  background-color: {B}; color: {F};
}}
window.island-settings decoration {{
  border-radius: 22px; border: 1px solid {f(0.08)};
  box-shadow: 0 12px 40px rgba(0,0,0,0.55);
}}
window.island-settings headerbar {{
  background: {B}; border: none; box-shadow: none; color: {F};
  border-radius: 22px 22px 0 0; padding: 10px 12px; min-height: 0;
}}
window.island-settings headerbar button,
window.island-settings button {{
  background: {f(0.06)}; color: {F}; border: none; box-shadow: none;
  border-radius: 999px; padding: 6px 14px; text-shadow: none; -gtk-icon-shadow: none;
}}
window.island-settings button:hover {{ background: {f(0.12)}; }}
window.island-settings button:active {{ background: {f(0.2)}; }}
window.island-settings headerbar button.wincontrol {{
  padding: 0; margin: 0 2px; min-width: 28px; min-height: 28px; border-radius: 999px;
  background: {f(0.06)}; color: {F};
}}
window.island-settings headerbar button.wincontrol:hover {{ background: {f(0.14)}; }}
window.island-settings headerbar button.wincontrol.close:hover {{
  background: rgb(220,60,60); color: #ffffff;
}}
window.island-settings stackswitcher button {{
  background: transparent; color: {f(0.6)}; margin: 0 2px; font-weight: 600;
}}
window.island-settings stackswitcher button:checked {{ background: {f(0.14)}; color: {F}; }}
window.island-settings scrolledwindow, window.island-settings viewport,
window.island-settings stack {{ background: transparent; }}
window.island-settings label.section {{
  color: {f(0.5)}; font-size: 11px; font-weight: 700; letter-spacing: 1px; margin-left: 6px;
}}
window.island-settings frame > border {{ border: none; }}
window.island-settings list {{
  background: {f(0.05)}; color: {F}; border-radius: 18px;
}}
window.island-settings list row {{ background: transparent; border-radius: 18px; }}
window.island-settings list row:hover {{ background: transparent; }}
window.island-settings list row + row {{ border-top: 1px solid {f(0.06)}; }}
window.island-settings label.dim-label {{ color: {f(0.55)}; opacity: 1; font-size: 12px; }}
window.island-settings switch {{
  background: {f(0.18)}; border: none; border-radius: 999px; min-height: 26px;
}}
window.island-settings switch:checked {{ background: {A}; }}
window.island-settings switch slider {{
  background: #ffffff; border: none; border-radius: 999px; box-shadow: 0 1px 3px rgba(0,0,0,0.4);
  min-width: 22px; min-height: 22px; margin: 2px;
}}
window.island-settings entry, window.island-settings spinbutton {{
  background: {f(0.08)}; color: {F}; border: 1px solid transparent; border-radius: 12px;
  box-shadow: none; caret-color: {A};
}}
window.island-settings entry:focus, window.island-settings spinbutton:focus {{
  border-color: {A};
}}
window.island-settings spinbutton entry {{ background: transparent; border: none; }}
window.island-settings spinbutton button {{ border-radius: 999px; padding: 4px 8px; background: transparent; }}
window.island-settings combobox button {{ border-radius: 12px; }}
window.island-settings button.color {{ padding: 4px; border-radius: 999px; }}
window.island-settings button.color colorswatch {{ border-radius: 999px; min-width: 28px; min-height: 18px; }}
window.island-settings flowboxchild {{ background: transparent; }}
window.island-settings flowboxchild button {{ background: transparent; border-radius: 16px; }}
window.island-settings flowboxchild button:hover {{ background: {f(0.08)}; }}
window.island-settings menu, window.island-settings .menu {{ background: {B}; color: {F}; }}
window.island-settings list row > box:disabled {{ opacity: 0.45; }}
window.island-settings entry.error {{ border-color: #ff5f57; }}
window.island-settings label.ok {{ color: {A}; }}
window.island-settings label.code {{
  font-family: monospace; background: {f(0.08)}; border-radius: 8px; padding: 4px 8px;
}}
window.island-settings button.suggested {{ background: {A}; color: #000; font-weight: 700; }}
"""


def autostart_enabled():
    return os.path.exists(AUTOSTART)


def set_autostart(enabled):
    if enabled:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        with open(AUTOSTART, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=linux-island\n"
                    "Comment=Dynamic island no painel\n"
                    f"Exec={RUN_SH}\nX-GNOME-Autostart-Delay=2\nNoDisplay=true\n")
    elif os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)


class Settings(SettingsThemesMixin, SettingsPagesMixin, Gtk.Window):
    def __init__(self, cfg, app=None, web=None, water=None, agenda=None):
        super().__init__(title=_("linux-island — Configurações"))
        if app:
            self.set_application(app)
        self.cfg = cfg
        self.web = web
        self.water = water
        self.agenda = agenda
        self._sync = {}  # chave -> função que atualiza o widget a partir da config
        self.set_default_size(520, 560)
        self.set_icon_name("preferences-system")
        self.get_style_context().add_class("island-settings")
        self._css = Gtk.CssProvider()
        self._css.connect("parsing-error", lambda _p, sec, err: print(
            f"[island] CSS das configurações, linha {sec.get_start_line() + 1}: {err.message}"))
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        self._restyle()

        # os botões de janela são nossos (ícones vetoriais): os do tema do sistema saíam
        # deslocados com este CSS e, com cor fixa, sumiriam num tema claro
        header = Gtk.HeaderBar(show_close_button=False)
        header.set_title(_("Configurações"))
        header.pack_end(self._window_controls())
        reset = Gtk.Button(label=_("Restaurar padrões"))
        reset.connect("clicked", lambda *_a: self.cfg.reset())
        header.pack_end(reset)
        self.set_titlebar(header)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        switcher = Gtk.StackSwitcher(stack=stack)
        header.set_custom_title(switcher)
        stack.add_titled(self._page_appearance(), "look", _("Aparência"))
        stack.add_titled(self._page_clock_weather(), "info", _("Relógio e clima"))
        stack.add_titled(self._page_behavior(), "behavior", _("Comportamento"))
        stack.add_titled(self._page_notifications(), "notifications", _("Notificações"))
        stack.add_titled(self._page_focus(), "focus", _("Foco"))
        if water is not None:
            stack.add_titled(self._page_water(), "water", _("Água"))
        if agenda is not None:
            stack.add_titled(self._page_agenda(), "agenda", _("Agenda"))
        if web is not None:
            stack.add_titled(self._page_spotify(), "spotify", _("Spotify"))
        self._stack = stack
        self.add(stack)

        cfg.connect(self._on_config)
        self.connect("destroy", lambda *_a: (
            cfg.disconnect(self._on_config),
            Gtk.StyleContext.remove_provider_for_screen(self.get_screen(), self._css)))
        self.show_all()

    def _window_controls(self):
        box = Gtk.Box(spacing=0)
        box.set_margin_start(6)

        def make(glyph, tip, cb, extra=None):
            b, g = glyph_button(glyph, 14, cb, tip)
            ctx = b.get_style_context()
            ctx.remove_class("control")
            ctx.add_class("wincontrol")
            if extra:
                ctx.add_class(extra)
            box.pack_start(b, False, False, 0)
            return g

        make("win_min", _("Minimizar"), self.iconify)
        self._max_glyph = make("win_max", _("Maximizar"), self._toggle_maximize)
        make("win_close", _("Fechar"), self.close, "close")
        self.connect("window-state-event", self._on_window_state)
        return box

    def _toggle_maximize(self):
        self.unmaximize() if self.is_maximized() else self.maximize()

    def _on_window_state(self, _w, ev):
        maximized = bool(ev.new_window_state & Gdk.WindowState.MAXIMIZED)
        self._max_glyph.set_glyph("win_restore" if maximized else "win_max")
        self._max_glyph.get_parent().set_tooltip_text(_("Restaurar") if maximized
                                                      else _("Maximizar"))
        return False

    def show_page(self, name):
        if self._stack.get_child_by_name(name):
            self._stack.set_visible_child_name(name)

    def _restyle(self):
        self._css.load_from_data(settings_css(self.cfg).encode())

    def _on_config(self, key):
        if key in ("bg_color", "text_color", "accent_auto", "accent_color", "accent_follow_kde"):
            self._restyle()
        if key in THEME_KEYS and hasattr(self, "_theme_status"):
            self._update_theme_status()
        fn = self._sync.get(key)
        if fn:
            fn()

    # --- construção de linhas ------------------------------------------
    @staticmethod
    def _page():
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for side in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{side}")(20)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.add(box)
        return scroll, box

    @staticmethod
    def _group(parent, title):
        lb = Gtk.Label(label=_(title).upper(), xalign=0)
        lb.get_style_context().add_class("section")
        frame = Gtk.Frame()
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        frame.add(listbox)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.pack_start(lb, False, False, 0)
        box.pack_start(frame, False, False, 0)
        parent.pack_start(box, False, False, 0)
        return listbox

    @staticmethod
    def _row(listbox, title, widget, subtitle=None):
        row = Gtk.Box(spacing=12)
        for side in ("top", "bottom", "start", "end"):
            getattr(row, f"set_margin_{side}")(10 if side in ("top", "bottom") else 12)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        t = Gtk.Label(label=_(title), xalign=0)
        texts.pack_start(t, False, False, 0)
        if subtitle:
            s = Gtk.Label(label=_(subtitle), xalign=0)
            s.set_line_wrap(True)
            s.get_style_context().add_class("dim-label")
            texts.pack_start(s, False, False, 0)
        widget.set_valign(Gtk.Align.CENTER)
        row.pack_start(texts, True, True, 0)
        row.pack_end(widget, False, False, 0)
        listbox.add(row)
        return row

    # --- controles ligados à config ------------------------------------
    def _switch(self, key):
        sw = Gtk.Switch(active=self.cfg[key])
        sw.connect("notify::active", lambda w, _p: self.cfg.set(key, w.get_active()))
        self._sync[key] = lambda: sw.set_active(self.cfg[key])
        return sw

    def _color(self, key, alpha=False):
        btn = Gtk.ColorButton(use_alpha=alpha)
        btn.set_rgba(rgba(self.cfg[key]))
        btn.connect("color-set", lambda b: self.cfg.set(key, b.get_rgba().to_string()))
        self._sync[key] = lambda: btn.set_rgba(rgba(self.cfg[key]))
        return btn

    def _spin(self, key, lo, hi, step=1):
        sp = Gtk.SpinButton.new_with_range(lo, hi, step)
        sp.set_value(self.cfg[key])
        sp.connect("value-changed", lambda w: self.cfg.set(key, int(w.get_value())))
        self._sync[key] = lambda: sp.set_value(self.cfg[key])
        return sp

    def _text_entry(self, key, max_len, placeholder):
        """Campo de texto ligado à config, salvando depois de uma pausa na digitação."""
        entry = Gtk.Entry(text=self.cfg[key], placeholder_text=_(placeholder))
        entry.set_width_chars(22)
        entry.set_max_length(max_len)
        pending = {"id": None}

        def commit(*_a):
            if pending["id"]:
                GLib.source_remove(pending["id"])
                pending["id"] = None
            self.cfg.set(key, entry.get_text().strip())
            return False

        def changed(*_a):
            if pending["id"]:
                GLib.source_remove(pending["id"])
            pending["id"] = GLib.timeout_add(800, commit)

        entry.connect("changed", changed)
        entry.connect("activate", commit)
        self._sync[key] = lambda: (entry.get_text().strip() != self.cfg[key]
                                   and entry.set_text(self.cfg[key]))
        return entry

    @staticmethod
    def _monitor_options():
        from gi.repository import Gdk
        display = Gdk.Display.get_default()
        opts = [("0", "Automático")]
        for i in range(display.get_n_monitors()):
            g = display.get_monitor(i).get_geometry()
            opts.append((str(i + 1), "Monitor {n} ({w}×{h})".format(n=i + 1, w=g.width, h=g.height)))
        return opts

    def _choice(self, key, options):
        combo = Gtk.ComboBoxText()
        for value, label in options:
            combo.append(value, _(label))
        combo.set_active_id(self.cfg[key])
        combo.connect("changed", lambda c: c.get_active_id() and self.cfg.set(key, c.get_active_id()))
        self._sync[key] = lambda: combo.set_active_id(self.cfg[key])
        return combo

    # --- páginas --------------------------------------------------------
    def _page_appearance(self):
        scroll, page = self._page()

        self._themes_group(page)
        self._auto_theme_group(page)

        colors = self._group(page, "Cores")
        self._row(colors, "Fundo", self._color("bg_color", alpha=True),
                  "Use a transparência para um efeito de vidro")
        self._row(colors, "Texto e ícones", self._color("text_color"))
        follow_row = self._row(colors, "Seguir a cor de destaque do KDE",
                               self._switch("accent_follow_kde"),
                               "Usa a cor de destaque das configurações do sistema e acompanha "
                               "quando você a troca")
        auto_row = self._row(colors, "Destaque automático", self._switch("accent_auto"),
                             "Equalizador e barra de progresso na cor da capa do álbum")
        accent_row = self._row(colors, "Cor de destaque", self._color("accent_color"))

        def accent_rows():
            follow = self.cfg["accent_follow_kde"]   # seguir o KDE manda sobre as outras duas
            auto_row.set_sensitive(not follow)
            accent_row.set_sensitive(not follow and not self.cfg["accent_auto"])

        accent_rows()
        for key in ("accent_auto", "accent_follow_kde"):
            prev = self._sync[key]
            self._sync[key] = lambda p=prev: (p(), accent_rows())

        alerts = self._group(page, "Cores dos alertas")
        self._row(alerts, "Água", self._color("color_water"), "Lembrete de beber água")
        self._row(alerts, "Reunião", self._color("color_meeting"), "Aviso de reunião da agenda")
        self._row(alerts, "Foco", self._color("color_focus"),
                  "Pomodoro, fim do foco e gasto acima do limite")
        self._row(alerts, "Claude Code", self._color("color_claude"),
                  "Gráficos e botões da página do Claude Code")

        shape = self._group(page, "Forma")
        self._row(shape, "Arredondamento expandida", self._spin("radius_expanded", 8, 48),
                  "Raio dos cantos, em px")
        self._row(shape, "Arredondamento fechada", self._spin("radius_compact", 4, 24),
                  "Raio dos cantos de baixo com a ilha fechada, em px")
        self._row(shape, "Borda sutil", self._switch("border"))
        self._row(shape, "Efeito vidro", self._switch("glass_style"),
                  "Brilho no topo e aro de luz, como o vidro da Apple")
        self._row(shape, "Desfoque do fundo", self._switch("glass_blur"),
                  "Usa o desfoque do KDE por trás do vidro (precisa do efeito Desfoque ligado)")
        self._row(shape, "Estilo entalhe", self._switch("notch_style"),
                  "Colada no topo, com as quinas de cima côncavas que se fundem à borda da tela")
        self._row(shape, "Curva do entalhe", self._spin("notch_ear", 4, 32),
                  "Tamanho da curva que liga a ilha à borda da tela, em px (só no estilo entalhe)")
        return scroll

    def _page_clock_weather(self):
        scroll, page = self._page()
        clock = self._group(page, "Relógio")
        self._row(clock, "Formato 24 horas", self._switch("clock_24h"))
        self._row(clock, "Mostrar data na pílula", self._switch("show_date"))

        weather = self._group(page, "Clima")
        entry = Gtk.Entry(text=self.cfg["city"], placeholder_text=_("Detectar pelo IP"))
        entry.set_width_chars(18)
        entry.set_max_length(100)
        pending = {"id": None}

        def commit(*_):
            if pending["id"]:
                GLib.source_remove(pending["id"])
                pending["id"] = None
            self.cfg.set("city", entry.get_text().strip())
            return False

        def changed(*_):
            if pending["id"]:
                GLib.source_remove(pending["id"])
            pending["id"] = GLib.timeout_add(900, commit)

        entry.connect("changed", changed)
        entry.connect("activate", commit)
        self._sync["city"] = lambda: (entry.get_text().strip() != self.cfg["city"]
                                      and entry.set_text(self.cfg["city"]))
        self._row(weather, "Cidade", entry, "Deixe vazio para detectar pela sua conexão")
        self._row(weather, "Unidade", self._choice(
            "units", [("celsius", "Celsius (°C)"), ("fahrenheit", "Fahrenheit (°F)")]))
        self._row(weather, "Mostrar clima na pílula", self._switch("show_weather"))
        self._row(weather, "Mostrar uso da CPU na pílula", self._switch("show_cpu"))
        return scroll

    def _page_behavior(self):
        scroll, page = self._page()
        hover = self._group(page, "Expansão")
        self._row(hover, "Expandir ao passar o mouse", self._switch("hover_expand"),
                  "Desligado: só abre com clique")
        self._row(hover, "Atraso do hover (ms)", self._spin("hover_delay_ms", 0, 2000, 20))
        self._row(hover, "Atraso para recolher (ms)", self._spin("collapse_delay_ms", 0, 5000, 100))
        self._row(hover, "Mostrar a música nova na pílula", self._switch("peek_on_track"),
                  "Na troca de faixa a pílula se estica com título e artista por 4 s")
        self._row(hover, "Volume pela rolagem do mouse", self._switch("scroll_volume"),
                  "Role sobre a ilha para aumentar ou baixar o volume da música")

        players = self._group(page, "Players")
        self._row(players, "Ignorar players", self._text_entry("player_ignore", 300,
                                                                 "Ex.: firefox, chromium"),
                  "Nomes separados por vírgula — por exemplo, para não mostrar vídeos do navegador")

        pos = self._group(page, "Posição")
        self._row(pos, "Distância do topo (px)", self._spin("margin_top", 0, 200))
        self._row(pos, "Esconder no topo", self._switch("auto_hide"),
                  "A ilha sobe para fora da tela e desce com o mouse, notificações e alertas")
        self._row(pos, "Esconder depois de (s)", self._spin("auto_hide_delay_s", 1, 60))
        self._row(pos, "Monitor", self._choice("monitor", self._monitor_options()),
                  "Em qual tela a ilha aparece")

        look = self._group(page, "Animações e visual")
        self._row(look, "Velocidade das animações", self._choice("animations", [
            ("none", "Sem animação"), ("fast", "Rápida"), ("normal", "Normal"),
            ("relaxed", "Suave e lenta")]), "Vale na hora para as próximas transições")
        self._row(look, "Equalizador", self._choice("eq_style", [
            ("bars", "Barras"), ("mirror", "Espectro"), ("wave", "Onda"), ("dots", "Pontos"),
            ("pulse", "Pulso")]), "Desenho animado enquanto a música toca")
        self._row(look, "Capa do álbum", self._choice("art_glow", [
            ("none", "Simples"), ("glow", "Brilho em volta"), ("blur", "Fundo desfocado")]),
            "Brilho com a cor da capa ou um cartão com a capa desfocada atrás do player")

        self._pages_group(page)

        lang = self._group(page, "Idioma")
        self._row(lang, "Idioma da ilha", self._choice("language", LANGUAGES),
                  "Automático segue o idioma do sistema")
        restart = Gtk.Button(label=_("Reiniciar agora"))
        restart.connect("clicked", lambda *_a: self.get_application().restart())
        self._row(lang, "Aplicar o idioma", restart, "A ilha reinicia para trocar o idioma")

        system = self._group(page, "Sistema")
        sw = Gtk.Switch(active=autostart_enabled())
        sw.connect("notify::active", lambda w, _p: set_autostart(w.get_active()))
        self._row(system, "Iniciar com a sessão", sw)
        self._row(system, "Mostrar câmera e microfone em uso", self._switch("privacy_indicator"),
                  "Um ícone na pílula, ao lado da xícara, enquanto algum app usa a webcam ou o "
                  "microfone. Passe o mouse para ver quais apps")
        return scroll
