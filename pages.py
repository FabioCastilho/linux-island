"""Páginas da ilha expandida e prioridade do miolo da pílula (inclui o lembrete de água).

Mixin da janela Island; usa self.full, self.water, self.water_page, self.compact,
self.shell, self.cfg, self.app, self._timers e self._follow_size dela.
"""
from datetime import datetime

from gi.repository import Gio, Gtk

import anim
import pagelist
from i18n import _
from icons import glyph_button
from notifications import OWN_APP, parse_ignore

from pointer import log
from water import play_sound

TRANSITION_MS = 320            # duração-base; o valor real passa por anim.ms()
PAGES = pagelist.ALL_PAGES     # todas as páginas existentes (as visíveis vêm de _page_names)
PAGE_TITLES = {"home": "Início", "water": "Água", "agenda": "Agenda", "notifs": "Notificações",
               "focus": "Foco", "tasks": "Tarefas", "camera": "Câmera", "bluetooth": "Bluetooth",
               "system": "Sistema", "claude": "Claude Code", "sessions": "Sessões"}


class PagesMixin:
    def _build_pages(self):
        """Ilha expandida: páginas lado a lado (arrastar para o lado troca) + pontinhos."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pages = Gtk.Stack()
        self.pages.set_homogeneous(False)
        self.pages.set_interpolate_size(True)
        self.pages.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        anim.register(self.pages, TRANSITION_MS)
        for name, widget in (("home", self.full), ("water", self.water_page),
                             ("agenda", self.agenda_page), ("notifs", self.notifs_page),
                             ("focus", self.focus_page), ("tasks", self.tasks_page),
                             ("camera", self.camera_page), ("bluetooth", self.bluetooth_page),
                             ("system", self.system_page), ("claude", self.claude_page),
                             ("sessions", self.sessions_page)):
            self.pages.add_named(widget, name)
        box.pack_start(self.pages, False, False, 0)

        self.dots_box = Gtk.Box(spacing=6)
        self.dots_box.set_halign(Gtk.Align.CENTER)
        self.dots_box.set_valign(Gtk.Align.CENTER)
        self.dots = {}
        for name in PAGES:
            dot = Gtk.Button()
            dot.set_can_focus(False)
            dot.set_no_show_all(True)  # quem mostra ou esconde é _apply_pages
            dot.set_tooltip_text(_(PAGE_TITLES[name]))
            dot.get_style_context().add_class("page-dot")
            dot.connect("clicked", lambda _b, n=name: self.set_page(n))
            self.dots_box.pack_start(dot, False, False, 0)
            self.dots[name] = dot
        # faixa de baixo: setas nos cantos e os pontinhos no meio. Os pontinhos são minúsculos;
        # um clique que erra cairia no fundo da ilha e a fecharia. Por isso a faixa toda
        # engole cliques (EventBox) e só os botões reagem.
        foot = Gtk.Box(spacing=6)
        foot.set_margin_start(10)
        foot.set_margin_end(10)
        foot.set_margin_top(2)
        foot.set_margin_bottom(6)
        self.prev_btn, _g = glyph_button("left", 14, lambda: self.turn_page(-1),
                                         _("Página anterior"))
        self.next_btn, _g = glyph_button("right", 14, lambda: self.turn_page(1),
                                         _("Próxima página"))
        foot.pack_start(self.prev_btn, False, False, 0)
        foot.pack_start(self.dots_box, True, True, 0)
        foot.pack_end(self.next_btn, False, False, 0)
        catcher = Gtk.EventBox()
        catcher.set_visible_window(False)
        catcher.add(foot)
        for sig in ("button-press-event", "button-release-event"):
            catcher.connect(sig, lambda *_a: True)
        self.foot = catcher
        box.pack_start(catcher, False, False, 0)
        self._apply_pages()
        self._mark_dot("home")
        return box

    def _page_names(self):
        """Páginas visíveis, na ordem escolhida nas configurações. O Bluetooth só entra se o PC
        tiver um adaptador (some sozinho num desktop sem Bluetooth)."""
        names = pagelist.visible(self.cfg["pages_order"], self.cfg["pages_hidden"])
        bt = getattr(self, "bluetooth", None)
        return [n for n in names if n != "bluetooth" or (bt and bt.available)]

    def _apply_pages(self):
        """Pontinhos na ordem e só das páginas visíveis; sai da página se ela foi escondida."""
        names = self._page_names()
        for i, name in enumerate(names):
            self.dots_box.reorder_child(self.dots[name], i)
            self.dots[name].show()
        for name, dot in self.dots.items():
            if name not in names:
                dot.hide()
        self.foot.set_visible(len(names) > 1)
        cur = self.pages.get_visible_child_name()
        if cur not in names and not getattr(self, "_page_forced", False):
            self.set_page("home")
        self._update_arrows()
        self._follow_size()

    def _mark_dot(self, name):
        for n, dot in self.dots.items():
            ctx = dot.get_style_context()
            (ctx.add_class if n == name else ctx.remove_class)("active")

    def set_page(self, name, forced=False):
        """forced: página pedida de fora (linha de comando) mesmo que esteja escondida."""
        cur = self.pages.get_visible_child_name()
        if name == cur or name not in PAGES:
            return
        self._page_forced = forced
        if name == "water":
            self.water_page.update(self.cfg)
        elif name == "agenda":
            self.agenda_page.update(self.cfg)
        log("page", name)
        names = self._page_names()
        # a direção do deslize segue a ordem escolhida (o Stack só conhece a ordem de criação)
        forward = (names.index(name) > names.index(cur)
                   if name in names and cur in names else True)
        self.pages.set_visible_child_full(
            name, Gtk.StackTransitionType.SLIDE_LEFT if forward
            else Gtk.StackTransitionType.SLIDE_RIGHT)
        self._mark_dot(name)
        self._update_arrows()
        self._update_keyboard()
        self._update_badges()
        self._follow_size()

    def _update_arrows(self):
        """As setas apagam nas pontas (primeira e última página visíveis)."""
        names = self._page_names()
        cur = self.pages.get_visible_child_name()
        i = names.index(cur) if cur in names else 0
        self.prev_btn.set_sensitive(i > 0)
        self.next_btn.set_sensitive(i < len(names) - 1)

    def turn_page(self, step):
        """step=+1 próxima página (arrastar para a esquerda), -1 anterior."""
        names = self._page_names()
        cur = self.pages.get_visible_child_name()
        i = (names.index(cur) if cur in names else 0) + step
        if 0 <= i < len(names):
            self.set_page(names[i])

    def _update_badges(self):
        """Pontinho da página Notificações fica em destaque quando há não lidas."""
        ctx = self.dots["notifs"].get_style_context()
        unread = self.notif_history.unread > 0 and self.pages.get_visible_child_name() != "notifs"
        (ctx.add_class if unread else ctx.remove_class)("has-badge")

    def _alert_page(self):
        """Página do alerta mais importante (reunião > água), ou a inicial."""
        if self.agenda.alert:
            return "agenda"
        return "water" if self.water.alerting else "home"

    def _refresh_middle(self):
        """Miolo da pílula: notificação > faixa nova > fim do foco > reunião > água > relógio."""
        if "notif_peek" in self._timers:
            name = "notif"
        elif "track_peek" in self._timers:
            name = "track"
        elif "focus_alert" in self._timers:
            name = "focus"
        elif self.agenda.alert:
            self.meeting_pill.update(self.agenda.alert, datetime.now().astimezone())
            name = "meeting"
        elif self.water.alerting:
            name = "water"
        else:
            name = "info"
        self.compact.middle.set_visible_child_name(name)
        if name != "info":
            self.autohide_poke()  # algo a mostrar: a ilha desce se estava escondida
        self._follow_size()

    # --- notificações de outros apps ----------------------------------------
    def _on_notification(self, n):
        cfg = self.cfg
        if n.app.lower() == OWN_APP or n.app.lower() in parse_ignore(cfg["notif_ignore"]):
            return
        if cfg["notif_history"]:  # o histórico guarda também o que o não-perturbe silenciou
            self.notif_history.add(n)
        if not cfg["notif_enabled"] or cfg["notif_dnd"] or self.expanded:
            return
        log("notificação", n.app)
        last = self._notif_queue[-1] if self._notif_queue else self._notif_current
        if last and (last.app, last.summary, last.body) == (n.app, n.summary, n.body):
            return  # repetida
        self._notif_queue = (self._notif_queue + [n])[-5:]
        if "notif_peek" not in self._timers:
            self._show_next_notification()

    def _show_next_notification(self):
        if not self._notif_queue or self.expanded:
            self._notif_queue = []
            self._notif_current = None
            self._refresh_middle()
            return
        self._notif_current = self._notif_queue.pop(0)
        self.notif_pill.update(self._notif_current, self.cfg["notif_show_body"])
        self._later("notif_peek", self.cfg["notif_duration_s"] * 1000,
                    self._show_next_notification)
        self._refresh_middle()

    def open_notification_app(self):
        """Clique na pílula durante uma notificação: abre o app, se der para saber qual."""
        n = self._notif_current if "notif_peek" in self._timers else None
        if not n or not n.desktop_entry:
            return False
        try:
            info = Gio.DesktopAppInfo.new(n.desktop_entry + ".desktop")
        except TypeError:
            info = None
        if info is None:
            return False
        info.launch([], None)
        self._cancel("notif_peek")
        self._show_next_notification()
        return True

    # --- agenda ---------------------------------------------------------
    def _on_agenda_change(self):
        if self.pages.get_visible_child_name() == "agenda":
            self.agenda_page.update(self.cfg)
            self._follow_size()

    def _on_agenda_alert(self, ev):
        log("meeting alert", ev and ev["title"])
        ctx = self.shell.get_style_context()
        (ctx.add_class if ev else ctx.remove_class)("meeting-alert")
        self._refresh_middle()
        self._on_agenda_change()
        if self.expanded and not ev and self.pages.get_visible_child_name() == "agenda":
            return  # o usuário está olhando a agenda: não troca de página
        if not self.expanded:
            self.set_page(self._alert_page())

    def _on_agenda_status(self, text, ok):
        self._on_agenda_change()
        if self.app.settings:
            self.app.settings.set_agenda_status(text, ok)

    # --- água -----------------------------------------------------------
    def _on_water_change(self):
        goal = self.cfg["water_goal_ml"]
        self.alert_amount.set_text(f"{self.water.consumed}/{goal} ml")
        self.water_page.update(self.cfg)
        if self.app.settings:
            self.app.settings._water_refresh()
        self._follow_size()

    def _on_water_alert(self, alerting):
        log("water alert", alerting)
        ctx = self.shell.get_style_context()
        (ctx.add_class if alerting else ctx.remove_class)("water-alert")
        self._on_water_change()
        self._refresh_middle()
        if alerting and self.cfg["water_sound"]:
            play_sound(self.cfg["water_sound_name"], self.cfg["water_sound_volume"])
        if alerting and self.cfg["water_notify"]:
            self.app.notify_water(self.water.consumed, self.cfg["water_goal_ml"])
        elif not alerting:
            self.app.withdraw_water()

