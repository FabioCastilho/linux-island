"""Configurações persistentes em ~/.config/linux-island/config.json."""
import json
import os
import re

from gi.repository import Gdk, Gio, GLib

import anim
import pagelist
from logutil import warn

PATH = os.path.join(GLib.get_user_config_dir(), "linux-island", "config.json")

# chave -> (padrão, validador). Validadores recebem o valor lido do JSON e
# devolvem True se ele for aceitável; senão vale o padrão.
_is_bool = lambda v: isinstance(v, bool)  # noqa: E731


def _is_color(v):
    return isinstance(v, str) and Gdk.RGBA().parse(v)


def _int_range(lo, hi):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _choice(*opts):
    return lambda v: v in opts


SCHEMA = {
    # aparência
    "bg_color": ("rgba(0,0,0,1)", _is_color),
    "text_color": ("rgb(255,255,255)", _is_color),
    "accent_auto": (True, _is_bool),          # cor de destaque tirada da capa
    "accent_color": ("rgb(30,215,96)", _is_color),
    "border": (True, _is_bool),
    "radius_expanded": (30, _int_range(8, 48)),
    "radius_compact": (14, _int_range(4, 24)),   # cantos de baixo com a ilha fechada
    "notch_ear": (12, _int_range(4, 32)),        # curva côncava do estilo entalhe
    "glass_style": (False, _is_bool),         # vidro: brilho no topo e aro de luz
    "claude_alert": (True, _is_bool),         # avisa na pílula quando o Claude Code termina
    "keep_awake": (False, _is_bool),          # não deixar o PC suspender (lembra ao reiniciar)
    "glass_blur": (True, _is_bool),           # desfoque do fundo (KDE), com o vidro ligado
    "notch_style": (False, _is_bool),         # colada no topo, quinas côncavas (entalhe)
    # relógio
    "clock_24h": (True, _is_bool),
    "show_date": (True, _is_bool),
    # clima
    "city": ("", lambda v: isinstance(v, str) and len(v) <= 100),
    "units": ("celsius", _choice("celsius", "fahrenheit")),
    "show_weather": (True, _is_bool),
    "show_cpu": (True, _is_bool),             # anel de CPU na pílula
    # Spotify Web API (playlist e dispositivo); vazio = desligado
    "spotify_client_id": ("", lambda v: isinstance(v, str)
                          and (v == "" or re.fullmatch(r"[0-9a-fA-F]{32}", v) is not None)),
    # lembrete de água
    "water_enabled": (True, _is_bool),
    "water_goal_ml": (2000, _int_range(250, 8000)),
    "water_cup_ml": (250, _int_range(50, 1500)),
    "water_interval_min": (60, _int_range(5, 360)),
    "water_start_h": (8, _int_range(0, 23)),
    "water_end_h": (22, _int_range(1, 24)),
    "water_snooze_min": (10, _int_range(1, 120)),
    "water_notify": (False, _is_bool),
    "water_sound": (True, _is_bool),
    "water_sound_name": ("message-new-instant", _choice(
        "message-new-instant", "complete", "bell", "dialog-information",
        "window-attention", "alarm-clock-elapsed")),
    "water_sound_volume": (70, _int_range(0, 100)),
    # agenda (Google Calendar, agenda principal)
    "agenda_enabled": (True, _is_bool),
    "agenda_alert": (True, _is_bool),
    "agenda_lead_min": (10, _int_range(0, 60)),
    "agenda_days": (3, _int_range(1, 7)),
    "agenda_sound": (True, _is_bool),
    "agenda_sound_name": ("bell", _choice(
        "message-new-instant", "complete", "bell", "dialog-information",
        "window-attention", "alarm-clock-elapsed")),
    "agenda_sound_volume": (70, _int_range(0, 100)),
    # notificações de outros apps na pílula
    "notif_enabled": (True, _is_bool),
    "notif_dnd": (False, _is_bool),
    "notif_duration_s": (5, _int_range(2, 15)),
    "notif_show_body": (True, _is_bool),
    "notif_ignore": ("Spotify", lambda v: isinstance(v, str) and len(v) <= 500),
    # idioma da interface ("auto" segue o sistema)
    "language": ("auto", _choice("auto", "pt", "en", "es")),
    # players de mídia a ignorar (nomes separados por vírgula)
    "player_ignore": ("", lambda v: isinstance(v, str) and len(v) <= 300),
    # comportamento
    "hover_expand": (True, _is_bool),
    "peek_on_track": (True, _is_bool),
    "scroll_volume": (True, _is_bool),
    "hover_delay_ms": (120, _int_range(0, 2000)),
    "margin_top": (2, _int_range(0, 200)),
    "auto_hide": (False, _is_bool),            # sobe para fora da tela e desce quando precisa
    "auto_hide_delay_s": (4, _int_range(1, 60)),
    "monitor": ("0", _choice("0", *map(str, range(1, 11)))),  # 0 = automático, 1..10 = nº do monitor
    # páginas da ilha expandida: ordem (nomes separados por vírgula) e as escondidas
    "pages_order": ("", pagelist.valid_spec),
    "pages_hidden": ("", pagelist.valid_spec),
    # animações e enfeites
    "animations": ("normal", _choice("none", "fast", "normal", "relaxed")),
    "eq_style": ("bars", _choice("bars", "wave", "dots", "mirror", "pulse")),
    "art_glow": ("glow", _choice("none", "glow", "blur")),   # brilho ou fundo desfocado da capa
    "privacy_indicator": (True, _is_bool),       # ícones de câmera/microfone em uso
    # cores de alerta/identidade (fazem parte do tema)
    "color_water": ("rgb(41,158,245)", _is_color),
    "color_meeting": ("rgb(167,139,250)", _is_color),
    "color_focus": ("rgb(237,102,82)", _is_color),
    "color_claude": ("rgb(217,119,87)", _is_color),
    # tema automático (claro/escuro pelo KDE ou por horário) e cor de destaque do KDE
    "theme_auto": ("off", _choice("off", "kde", "schedule")),
    "theme_light": ("Claro", lambda v: isinstance(v, str) and 0 < len(v) <= 40),
    "theme_dark": ("Clássico", lambda v: isinstance(v, str) and 0 < len(v) <= 40),
    "theme_dark_from_h": (19, _int_range(0, 23)),   # escuro a partir desta hora...
    "theme_dark_to_h": (7, _int_range(0, 23)),      # ...até esta
    "accent_follow_kde": (False, _is_bool),          # destaque = cor de destaque do KDE
    # histórico de notificações (só na memória: some ao reiniciar a ilha)
    "notif_history": (True, _is_bool),
    "notif_history_max": (50, _int_range(10, 200)),
    # foco / pomodoro
    "pomo_focus_min": (25, _int_range(1, 180)),
    "pomo_short_min": (5, _int_range(1, 60)),
    "pomo_long_min": (15, _int_range(1, 120)),
    "pomo_rounds": (4, _int_range(2, 8)),                    # focos até a pausa longa
    "pomo_sound": (True, _is_bool),
    "pomo_auto_next": (False, _is_bool),                     # começa a próxima fase sozinho
    # Claude Code na pílula
    "claude_attention": (True, _is_bool),                    # avisa quando a sessão pede algo
    "claude_pill_cost": (False, _is_bool),                   # custo do dia ao lado do relógio
    "claude_daily_limit": (0, _int_range(0, 1000)),          # US$ por dia; 0 = sem limite
}


class Config:
    def __init__(self, overrides=None):
        self._values = {k: d for k, (d, _) in SCHEMA.items()}
        self._listeners = []
        self._save_id = None
        self._load()
        # overrides da linha de comando valem só para esta execução
        self._overrides = {k: v for k, v in (overrides or {}).items() if v is not None}

    def _load(self):
        try:
            with open(PATH) as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            warn("config inválida, usando padrões", e)
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if key in SCHEMA and SCHEMA[key][1](value):
                self._values[key] = value

    def __getitem__(self, key):
        return self._overrides.get(key, self._values[key])

    # --- edição externa do config.json: aplica ao vivo -----------------------
    def watch(self):
        """Observa o arquivo: o que mudar fora da ilha (editor, script) vale na hora."""
        self._reload_id = None
        gfile = Gio.File.new_for_path(PATH)
        try:
            self._monitor = gfile.monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        except GLib.Error:
            return
        self._monitor.connect("changed", self._on_file_changed)

    def _on_file_changed(self, *_a):
        if self._reload_id:
            GLib.source_remove(self._reload_id)
        self._reload_id = GLib.timeout_add(250, self._reload)

    def _reload(self):
        self._reload_id = None
        try:
            with open(PATH) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False  # arquivo no meio de uma escrita ou inválido: ignora
        if not isinstance(data, dict):
            return False
        for key, value in data.items():
            if key in SCHEMA and SCHEMA[key][1](value) and self._values[key] != value:
                self._values[key] = value
                for fn in list(self._listeners):
                    fn(key)
        return False

    def set(self, key, value):
        if key not in SCHEMA or not SCHEMA[key][1](value):
            raise ValueError(f"valor inválido para {key}: {value!r}")
        self._overrides.pop(key, None)  # mexeu na UI: vale o que foi escolhido
        if self._values[key] == value:
            return
        self._values[key] = value
        self._schedule_save()
        for fn in self._listeners:
            fn(key)

    def reset(self):
        for key, (default, _) in SCHEMA.items():
            self.set(key, default)

    def connect(self, fn):
        self._listeners.append(fn)

    def disconnect(self, fn):
        if fn in self._listeners:
            self._listeners.remove(fn)

    def _schedule_save(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(400, self._save)

    def _save(self):
        self._save_id = None
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._values, f, indent=2, ensure_ascii=False)
        os.replace(tmp, PATH)
        return False


def rgba(spec):
    c = Gdk.RGBA()
    c.parse(spec)
    return c


def css_color(c, alpha=None):
    a = c.alpha if alpha is None else c.alpha * alpha
    return f"rgba({round(c.red * 255)},{round(c.green * 255)},{round(c.blue * 255)},{a:.3f})"


def build_css(cfg):
    """CSS gerado a partir da configuração (cores e arredondamento)."""
    bg, fg = rgba(cfg["bg_color"]), rgba(cfg["text_color"])
    water, meeting = rgba(cfg["color_water"]), rgba(cfg["color_meeting"])
    focus, claude = rgba(cfg["color_focus"]), rgba(cfg["color_claude"])
    W, M, FO, CL = (css_color(c) for c in (water, meeting, focus, claude))
    border = f"1px solid {css_color(fg, 0.07)}" if cfg["border"] else "1px solid transparent"
    return f"""
.island {{ background-color: {css_color(bg)}; color: {css_color(fg)}; border: {border};
  transition: border-radius {anim.ms(320)}ms {anim.easing_css()}; }}
.island.drawn, .island.drawn.expanded, .island.drawn.water-alert, .island.drawn.meeting-alert,
.island.drawn.focus-alert {{
  background-color: transparent; border: none; box-shadow: none; animation: none;
}}
.island {{ border-radius: {cfg['radius_compact']}px; }}
.island.expanded {{ border-radius: {cfg['radius_expanded']}px; }}
.island .dim, .island .artist {{ color: {css_color(fg, 0.6)}; }}
.island .time {{ color: {css_color(fg, 0.55)}; }}
.island .control {{ color: {css_color(fg)}; }}
.island .control:hover {{ background-color: {css_color(fg, 0.12)}; }}
.island .control:active {{ background-color: {css_color(fg, 0.22)}; }}
.island .day {{ background-color: {css_color(fg, 0.05)}; }}
.island separator {{ background-color: {css_color(fg, 0.1)}; }}
.island.water-alert {{ border-color: {W}; }}
.island.meeting-alert {{ border-color: {M}; }}
@keyframes water-pulse {{
  from {{ border-color: {css_color(water, 0.95)}; }} to {{ border-color: {css_color(water, 0.25)}; }}
}}
@keyframes meeting-pulse {{
  from {{ border-color: {css_color(meeting, 0.95)}; }} to {{ border-color: {css_color(meeting, 0.25)}; }}
}}
@keyframes focus-pulse {{
  from {{ border-color: {css_color(focus, 0.95)}; }} to {{ border-color: {css_color(focus, 0.25)}; }}
}}
.island button.water-main {{ background: {W}; }}
.island button.water-main:hover {{ background: {css_color(water, 0.85)}; }}
.island .over {{ color: {FO}; }}
.island button.agenda-row {{
  background: transparent; border: none; box-shadow: none; padding: 6px 8px;
  border-radius: 12px; color: {css_color(fg)};
}}
.island button.agenda-row:hover {{ background: {css_color(fg, 0.07)}; }}
.island button.page-dot {{
  min-width: 6px; min-height: 6px; padding: 0; border: none; box-shadow: none;
  border-radius: 999px; background: {css_color(fg, 0.25)};
}}
.island button.page-dot.active {{ background: {css_color(fg, 0.9)}; min-width: 16px; }}
.island button.page-dot.has-badge {{ background: {FO}; }}
.island.focus-alert {{ border-color: {FO}; }}
.island button.power-btn {{
  background: {css_color(fg, 0.08)}; color: {css_color(fg)}; border: none; box-shadow: none;
  border-radius: 14px; padding: 8px 2px; text-shadow: none;
}}
.island button.power-btn.danger {{ background: rgba(220,60,60,0.16); color: rgb(255,120,115); }}
.island button.power-btn.danger:hover {{ background: rgba(220,60,60,0.30); }}
.island .power-lbl {{ font-size: 11px; font-weight: 600; }}
.island button.power-btn:hover {{ background: {css_color(fg, 0.16)}; }}
.island button.power-btn.armed {{ background: rgb(220,60,60); color: #ffffff; }}
.island .badge {{
  font-size: 10px; font-weight: 600; padding: 1px 8px; border-radius: 999px;
  background: {css_color(fg, 0.10)}; color: {css_color(fg, 0.75)};
}}
.island .session-row {{
  background: {css_color(fg, 0.05)}; border-radius: 14px; padding: 8px 10px;
}}
.island button.seg {{
  background: {css_color(fg, 0.08)}; color: {css_color(fg, 0.7)}; border: none; box-shadow: none;
  border-radius: 999px; padding: 2px 10px; font-size: 11px; min-height: 0; text-shadow: none;
}}
.island button.seg:hover {{ background: {css_color(fg, 0.16)}; }}
.island button.seg.active {{ background: {CL}; color: #ffffff; font-weight: 700; }}
.island button.water-snooze {{
  background: {css_color(fg, 0.08)}; color: {css_color(fg)}; border: none; box-shadow: none;
  border-radius: 999px; padding: 4px 12px; font-size: 11px;
}}
.island .row-card {{ background: {css_color(fg, 0.05)}; border-radius: 14px; padding: 8px 10px; }}
.island .row-card.unread {{ background: {css_color(fg, 0.09)}; }}
.island .row-card.done .row-title {{ color: {css_color(fg, 0.45)}; }}
.island button.chip {{
  background: {css_color(fg, 0.08)}; color: {css_color(fg, 0.8)}; border: none; box-shadow: none;
  border-radius: 999px; padding: 3px 12px; font-size: 11px; min-height: 0; text-shadow: none;
}}
.island button.chip:hover {{ background: {css_color(fg, 0.16)}; }}
.island button.chip:active {{ background: {css_color(fg, 0.26)}; }}
.island button.chip.active {{ background: {css_color(fg, 0.88)}; color: {css_color(bg)};
  font-weight: 700; }}
.island entry.quick-entry {{
  background: {css_color(fg, 0.07)}; color: {css_color(fg)}; border: none; box-shadow: none;
  border-radius: 12px; padding: 6px 10px; min-height: 0;
}}
.island entry.quick-entry:focus {{ background: {css_color(fg, 0.12)}; }}
.island .timer-clock {{ font-size: 30px; font-weight: 300; font-feature-settings: "tnum"; }}
.island .pill-chip {{ font-size: 12px; font-weight: 600; font-feature-settings: "tnum"; }}
.island .slim-bar trough {{ min-height: 4px; background: {css_color(fg, 0.14)}; border-radius: 4px; }}
.island .slim-bar highlight, .island .slim-bar progress {{ min-height: 4px; border-radius: 4px; }}
"""


def accent_tuple(spec):
    c = rgba(spec)
    return (c.red, c.green, c.blue)
