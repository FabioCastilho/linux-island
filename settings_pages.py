"""Abas extras da janela de configurações (Spotify; Água).

Mixin de settings.Settings: usa self.cfg, self.web, self._page, self._group,
self._row, self._switch, self._spin e self._sync de lá.
"""
from gi.repository import GLib, Gtk

import pagelist
from i18n import _


class SettingsPagesMixin:
    def _page_notifications(self):
        scroll, page = self._page()
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_markup(_("Quando um app manda uma notificação, a pílula se estica por alguns "
                         "segundos mostrando quem notificou e o que disse. Clique nela para "
                         "abrir o app."))
        intro.get_style_context().add_class("dim-label")
        page.pack_start(intro, False, False, 0)

        main = self._group(page, "Notificações")
        self._row(main, "Mostrar notificações na pílula", self._switch("notif_enabled"))
        self._row(main, "Não perturbe", self._switch("notif_dnd"),
                  "Pausa as notificações na ilha (as do sistema continuam normais)")
        self._row(main, "Duração (s)", self._spin("notif_duration_s", 2, 15))
        self._row(main, "Avisar quando o Claude Code terminar", self._switch("claude_alert"),
                  "A pílula mostra o projeto quando uma sessão termina e espera por você")
        self._row(main, "Mostrar o texto", self._switch("notif_show_body"),
                  "Desligado: só o título aparece, para mais privacidade")
        self._row(main, "Avisar quando o Claude Code pedir algo", self._switch("claude_attention"),
                  "Se a sessão entrar em outro estado além de trabalhando e aguardando")
        self._row(main, "Mostrar o gasto do dia do Claude Code",
                  self._switch("claude_pill_cost"),
                  "Valor estimado em dólar, ao lado do relógio")
        self._row(main, "Limite diário do Claude Code (US$)",
                  self._spin("claude_daily_limit", 0, 1000, 1),
                  "0 desliga. Ao passar do valor, o gasto fica vermelho e a ilha avisa uma vez por dia")

        hist = self._group(page, "Histórico")
        self._row(hist, "Guardar o histórico", self._switch("notif_history"),
                  "Só na memória: some ao reiniciar a ilha. Desligar apaga o que já foi guardado")
        self._row(hist, "Quantas guardar", self._spin("notif_history_max", 10, 200, 10))

        ignore = self._group(page, "Apps ignorados")
        entry = Gtk.Entry(text=self.cfg["notif_ignore"], placeholder_text=_("Ex.: Spotify, Slack"))
        entry.set_width_chars(26)
        entry.set_max_length(500)
        pending = {"id": None}

        def commit(*_):
            if pending["id"]:
                GLib.source_remove(pending["id"])
                pending["id"] = None
            self.cfg.set("notif_ignore", entry.get_text().strip())
            return False

        def changed(*_):
            if pending["id"]:
                GLib.source_remove(pending["id"])
            pending["id"] = GLib.timeout_add(800, commit)

        entry.connect("changed", changed)
        entry.connect("activate", commit)
        self._sync["notif_ignore"] = lambda: (
            entry.get_text().strip() != self.cfg["notif_ignore"]
            and entry.set_text(self.cfg["notif_ignore"]))
        self._row(ignore, "Não mostrar de", entry, "Nomes dos apps, separados por vírgula")
        return scroll

    def _page_agenda(self):
        from google_calendar import find_client_secret
        from water import SOUNDS, play_sound

        scroll, page = self._page()
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_markup(_("Mostra os eventos da sua agenda principal do <b>Google</b> e avisa "
                         "antes das reuniões. Funciona com contas pessoais e corporativas; "
                         "o acesso é <b>somente leitura</b>, a menos que você libere a "
                         "criação de eventos abaixo."))
        intro.get_style_context().add_class("dim-label")
        page.pack_start(intro, False, False, 0)

        account = self._group(page, "Conta Google")
        has_app = find_client_secret() is not None
        if not has_app:
            warn = Gtk.Label(xalign=0, wrap=True)
            warn.set_markup(_("As credenciais do app do Google não estão configuradas nesta "
                            "instalação — veja a seção <b>Agenda</b> do README."))
            warn.get_style_context().add_class("dim-label")
            box = Gtk.Box()
            for side in ("top", "bottom", "start", "end"):
                getattr(box, f"set_margin_{side}")(10 if side in ("top", "bottom") else 12)
            box.pack_start(warn, True, True, 0)
            account.add(box)
        self.ag_status = Gtk.Label(xalign=0)
        self.ag_button = Gtk.Button()
        self.ag_button.set_sensitive(has_app)
        self.ag_button.connect("clicked", lambda *_a: (
            self.agenda.disconnect() if self.agenda.connected else self.agenda.login()))
        self._row(account, "Status", self.ag_button).get_children()[0].pack_start(
            self.ag_status, False, False, 0)

        write = self._group(page, "Criar eventos")
        self._row(write, "Permitir criar eventos", self._switch("agenda_write"),
                  "Pede ao Google a permissão de eventos. O app só cria, nunca edita nem "
                  "apaga. Desligar revoga a permissão e você reconecta em modo leitura.")

        show = self._group(page, "Exibição")
        self._row(show, "Mostrar agenda", self._switch("agenda_enabled"))
        self._row(show, "Dias à frente", self._spin("agenda_days", 1, 7))

        alert = self._group(page, "Aviso de reunião")
        self._row(alert, "Avisar na pílula", self._switch("agenda_alert"),
                  "A pílula mostra a reunião com contagem regressiva")
        self._row(alert, "Quanto antes (min)", self._spin("agenda_lead_min", 0, 60, 5))
        self._row(alert, "Tocar som", self._switch("agenda_sound"))
        self._row(alert, "Som", self._choice("agenda_sound_name", SOUNDS))
        test = Gtk.Button(label=_("Testar"))
        test.connect("clicked", lambda *_a: play_sound(self.cfg["agenda_sound_name"],
                                                      self.cfg["agenda_sound_volume"]))
        vol = Gtk.Box(spacing=8)
        vol.pack_start(self._spin("agenda_sound_volume", 0, 100, 10), False, False, 0)
        vol.pack_start(test, False, False, 0)
        self._row(alert, "Volume (%)", vol)
        return scroll

    def set_agenda_status(self, text, ok):
        if not hasattr(self, "ag_status"):
            return
        self.ag_status.set_text(text)
        ctx = self.ag_status.get_style_context()
        (ctx.add_class if ok else ctx.remove_class)("ok")
        (ctx.remove_class if ok else ctx.add_class)("dim-label")
        connected = self.agenda.connected
        self.ag_button.set_label(_("Sair da conta") if connected else _("Entrar com Google"))
        bctx = self.ag_button.get_style_context()
        (bctx.remove_class if connected else bctx.add_class)("suggested")

    def _page_water(self):
        scroll, page = self._page()
        main = self._group(page, "Lembrete")
        self._row(main, "Lembrar de beber água", self._switch("water_enabled"))
        self._row(main, "Intervalo (min)", self._spin("water_interval_min", 5, 360, 5),
                  "Tempo desde o último copo até o próximo lembrete")
        self._row(main, "Adiar por (min)", self._spin("water_snooze_min", 1, 120, 1))
        self._row(main, "Notificação do sistema", self._switch("water_notify"),
                  "Além do aviso na ilha, mostra uma notificação com Bebi e Adiar")

        from water import SOUNDS, play_sound  # import local: só a aba usa

        sound = self._group(page, "Aviso sonoro")
        self._row(sound, "Tocar som no lembrete", self._switch("water_sound"))
        self._row(sound, "Som", self._choice("water_sound_name", SOUNDS))
        test = Gtk.Button(label=_("Testar"))
        test.connect("clicked", lambda *_a: play_sound(self.cfg["water_sound_name"],
                                                      self.cfg["water_sound_volume"]))
        vol = Gtk.Box(spacing=8)
        vol.pack_start(self._spin("water_sound_volume", 0, 100, 10), False, False, 0)
        vol.pack_start(test, False, False, 0)
        self._row(sound, "Volume (%)", vol)

        goal = self._group(page, "Meta")
        self._row(goal, "Meta diária (ml)", self._spin("water_goal_ml", 250, 8000, 250))
        self._row(goal, "Tamanho do copo (ml)", self._spin("water_cup_ml", 50, 1500, 50),
                  "Quanto soma cada clique em + na ilha")

        hours = self._group(page, "Horário")
        self._row(hours, "Começa às (h)", self._spin("water_start_h", 0, 23))
        self._row(hours, "Termina às (h)", self._spin("water_end_h", 1, 24),
                  "Se o fim não for depois do início, lembra o dia todo")

        today = self._group(page, "Hoje")
        self.water_today = Gtk.Label(xalign=0)
        reset = Gtk.Button(label=_("Zerar hoje"))
        reset.connect("clicked", lambda *_a: (self.water.reset_day(), self._water_refresh()))
        self._row(today, "Consumido", reset).get_children()[0].pack_start(
            self.water_today, False, False, 0)
        self._water_refresh()
        return scroll

    def _water_refresh(self):
        if hasattr(self, "water_today"):
            self.water_today.set_text(
                _("{feito} de {meta} ml").format(feito=self.water.consumed,
                                                 meta=self.cfg["water_goal_ml"])
                + f" · {self.water.status()}")
            self.water_today.get_style_context().add_class("dim-label")

    def _page_spotify(self):
        from spotify_web import REDIRECT_URI  # import local: módulo opcional da UI

        scroll, page = self._page()
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_markup(_(
            "Mostra a <b>playlist</b> que está tocando e o <b>dispositivo</b> (celular, "
            "caixa de som, TV…). O Spotify não expõe isso localmente, então é preciso "
            "conectar sua conta pela Web API com um app seu."))
        intro.get_style_context().add_class("dim-label")
        page.pack_start(intro, False, False, 0)

        steps = self._group(page, "Como configurar")
        for n, text in enumerate([
            'Abra <a href="https://developer.spotify.com/dashboard">developer.spotify.com/'
            'dashboard</a> e crie um app (a conta dona precisa ser Premium).',
            "Em <b>Redirect URIs</b> adicione o endereço abaixo e marque <b>Web API</b>.",
            "Salve, copie o <b>Client ID</b> do app e cole aqui embaixo.",
        ], 1):
            lb = Gtk.Label(xalign=0, wrap=True)
            lb.set_markup(f"{n}. {_(text)}")
            row = Gtk.Box()
            for side in ("top", "bottom", "start", "end"):
                getattr(row, f"set_margin_{side}")(10 if side in ("top", "bottom") else 12)
            row.pack_start(lb, True, True, 0)
            steps.add(row)
        uri = Gtk.Label(label=REDIRECT_URI, selectable=True)
        uri.get_style_context().add_class("code")
        copy = Gtk.Button(label=_("Copiar"))
        copy.connect("clicked", lambda *_a: Gtk.Clipboard.get_default(
            self.get_display()).set_text(REDIRECT_URI, -1))
        box = Gtk.Box(spacing=8)
        box.pack_start(uri, False, False, 0)
        box.pack_start(copy, False, False, 0)
        self._row(steps, "Redirect URI", box)

        account = self._group(page, "Conta")
        entry = Gtk.Entry(text=self.cfg["spotify_client_id"], placeholder_text=_("32 caracteres"))
        entry.set_width_chars(34)
        entry.set_max_length(32)

        def changed(*_):
            text = entry.get_text().strip()
            valid = text == "" or (len(text) == 32 and all(c in "0123456789abcdefABCDEF"
                                                          for c in text))
            ctx = entry.get_style_context()
            (ctx.remove_class if valid else ctx.add_class)("error")
            if valid:
                self.cfg.set("spotify_client_id", text)

        entry.connect("changed", changed)
        self._sync["spotify_client_id"] = lambda: (
            entry.get_text().strip() != self.cfg["spotify_client_id"]
            and entry.set_text(self.cfg["spotify_client_id"]))
        self._row(account, "Client ID", entry)

        self.sp_status = Gtk.Label(xalign=0)
        self.sp_button = Gtk.Button()
        self.sp_button.connect("clicked", self._spotify_clicked)
        self._row(account, "Status", self.sp_button).get_children()[0].pack_start(
            self.sp_status, False, False, 0)
        return scroll

    def _spotify_clicked(self, *_):
        if self.web.connected:
            self.web.disconnect()
        else:
            self.web.login()

    def set_spotify_status(self, text, ok):
        if not hasattr(self, "sp_status"):
            return
        self.sp_status.set_text(text)
        ctx = self.sp_status.get_style_context()
        (ctx.add_class if ok else ctx.remove_class)("ok")
        if not ok:
            ctx.add_class("dim-label")
        else:
            ctx.remove_class("dim-label")
        connected = self.web.connected
        self.sp_button.set_label(_("Desconectar") if connected else _("Conectar"))
        bctx = self.sp_button.get_style_context()
        (bctx.remove_class if connected else bctx.add_class)("suggested")

    # --- foco / pomodoro -------------------------------------------------------
    def _page_focus(self):
        scroll, page = self._page()
        intro = Gtk.Label(xalign=0, wrap=True)
        intro.set_text(_("Ciclos de foco e pausa. Enquanto roda, a pílula mostra o tempo que "
                         "falta; no fim, ela avisa e toca um som."))
        intro.get_style_context().add_class("dim-label")
        page.pack_start(intro, False, False, 0)
        g = self._group(page, "Pomodoro")
        self._row(g, "Foco (min)", self._spin("pomo_focus_min", 1, 180))
        self._row(g, "Pausa curta (min)", self._spin("pomo_short_min", 1, 60))
        self._row(g, "Pausa longa (min)", self._spin("pomo_long_min", 1, 120))
        self._row(g, "Focos até a pausa longa", self._spin("pomo_rounds", 2, 8))
        self._row(g, "Tocar um som no fim", self._switch("pomo_sound"))
        self._row(g, "Começar a próxima fase sozinho", self._switch("pomo_auto_next"),
                  "Desligado: espera você iniciar depois de cada fase")
        return scroll

    # --- páginas da ilha: ordem e visibilidade -----------------------------------
    def _pages_group(self, page):
        from pages import PAGE_TITLES  # evita importar a janela da ilha ao abrir só o módulo
        listbox = self._group(page, "Páginas da ilha")
        state = {"pending": False}

        def toggle(name, on):
            hidden = {p for p in pagelist.split(self.cfg["pages_hidden"])}
            hidden.discard(name) if on else hidden.add(name)
            self.cfg.set("pages_hidden",
                         ",".join(p for p in pagelist.ALL_PAGES if p in hidden))

        def move(name, step):
            self.cfg.set("pages_order", pagelist.move(self.cfg["pages_order"], name, step))

        def rebuild():
            state["pending"] = False
            for row in listbox.get_children():
                listbox.remove(row)
            order = pagelist.order(self.cfg["pages_order"])
            hidden = set(pagelist.split(self.cfg["pages_hidden"]))
            for i, name in enumerate(order):
                box = Gtk.Box(spacing=2)
                for icon, step, ok in (("go-up-symbolic", -1, i > 0),
                                       ("go-down-symbolic", 1, i < len(order) - 1)):
                    b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
                    b.set_relief(Gtk.ReliefStyle.NONE)
                    b.set_sensitive(ok)
                    b.connect("clicked", lambda _b, n=name, st=step: move(n, st))
                    box.pack_start(b, False, False, 0)
                sw = Gtk.Switch(active=name not in hidden)
                sw.set_sensitive(name not in pagelist.ALWAYS_SHOWN)
                sw.set_valign(Gtk.Align.CENTER)
                sw.set_margin_start(8)
                sw.connect("notify::active", lambda w, _p, n=name: toggle(n, w.get_active()))
                box.pack_start(sw, False, False, 0)
                self._row(listbox, PAGE_TITLES[name], box)
            listbox.show_all()
            return False

        def schedule():
            # reconstruir dentro do próprio sinal do botão apagaria o botão no meio do clique
            if not state["pending"]:
                state["pending"] = True
                GLib.idle_add(rebuild)

        rebuild()
        self._sync["pages_order"] = schedule
        self._sync["pages_hidden"] = schedule
