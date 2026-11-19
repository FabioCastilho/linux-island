"""Desenha os widgets novos em superfícies na memória (sem abrir janela) para pegar erros.

Precisa de uma sessão gráfica para o GTK iniciar; sem ela, os testes são pulados.
"""
import os
import tempfile
import unittest

import _path  # noqa: F401
import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk  # noqa: E402

HAVE_DISPLAY = Gtk.init_check()[0]


def paint(widget, w=120, h=60):
    """Chama o handler 'draw' do widget com um contexto cairo de verdade."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    widget.set_size_request(w, h)
    widget.size_allocate(widget.get_allocation()) if False else None
    return widget.emit("draw", cr)


class FakeCfg(dict):
    pass


def make_cfg():
    import config
    return FakeCfg({k: d for k, (d, _v) in config.SCHEMA.items()})


@unittest.skipUnless(HAVE_DISPLAY, "sem sessão gráfica")
class WidgetTests(unittest.TestCase):
    def test_every_glyph_draws(self):
        from icons import GLYPHS, Glyph
        for name in GLYPHS:
            with self.subTest(glyph=name):
                paint(Glyph(name, 16), 16, 16)

    def test_every_equalizer_style_draws_playing_and_paused(self):
        from widgets import EQ_STYLES, Equalizer
        for style in EQ_STYLES:
            for playing in (True, False):
                with self.subTest(style=style, playing=playing):
                    eq = Equalizer(20, 18)
                    eq.set_style(style)
                    eq.playing = playing
                    paint(eq, 20, 18)
        eq = Equalizer(14, 12)
        eq.set_style("não existe")
        self.assertEqual(eq.style, "bars")

    def test_art_glow_changes_size_and_draws(self):
        from widgets import GLOW_PAD, Art
        art = Art(52, 12)
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 64, 64)
        art.set_source(pb)
        art.set_glow((0.9, 0.3, 0.2))
        self.assertEqual(art.get_size_request(), (52 + 2 * GLOW_PAD, 52 + 2 * GLOW_PAD))
        paint(art, 68, 68)
        art.set_glow(None)
        self.assertEqual(art.get_size_request(), (52, 52))

    def test_expanded_card_modes(self):
        from views import Expanded
        full = Expanded(object())
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 64, 64)
        full.set_art_pixbuf(pb)
        for mode in ("none", "glow", "blur"):
            with self.subTest(mode=mode):
                full.set_art_mode(mode, (0.5, 0.5, 0.5))
                paint(full.music_box, 300, 120)
        full.set_art_pixbuf(None)
        paint(full.music_box, 300, 120)

    def test_compact_pill_chips(self):
        from views import Compact
        c = Compact()
        c.set_focus_timer("12:34")
        self.assertTrue(c.focus_rev.get_reveal_child())
        c.set_focus_timer(None)
        self.assertFalse(c.focus_rev.get_reveal_child())
        c.set_cost("US$ 1.23")
        self.assertTrue(c.cost_rev.get_reveal_child())

    def test_pages_build_and_update(self):
        from focus import Focus
        from focus_view import FocusPage
        from notif_history import NotificationHistory
        from notifs_view import NotifsPage
        from tasks import Tasks
        from tasks_view import TasksPage

        class N:
            app, summary, body, icon, desktop_entry = "App", "Oi", "corpo", None, ""

        cfg = make_cfg()
        focus = Focus(cfg)
        page = FocusPage(focus)
        for phase in ("focus", "short", "long", "timer"):
            focus.set_phase(phase)
            page.update()
        focus.start()
        page.update()
        paint(page.ring, 132, 132)
        paint(page.dots, 80, 10)

        hist = NotificationHistory()
        notifs = NotifsPage(hist)
        hist.add(N())
        notifs.update()
        self.assertTrue(notifs.empty.get_no_show_all())

        with tempfile.TemporaryDirectory() as d:
            tasks = Tasks(os.path.join(d, "t.json"))
            tpage = TasksPage(tasks)
            tasks.add("uma")
            tasks.add("duas")
            tasks.toggle(tasks.items[0]["id"])
            tpage.update()
            self.assertEqual(len(tpage.listbox.get_children()), 2)
            tpage.entry.set_text("três")
            tpage._add()
            self.assertEqual(len(tasks.items), 3)
            self.assertEqual(tpage.entry.get_text(), "")

    def test_day_chart_draws_with_and_without_limit_and_cost(self):
        from datetime import date, timedelta
        from claude_view import DayChart
        today = date.today()
        days = [(today - timedelta(days=6 - i), 1000 * i, 0.5 * i) for i in range(7)]
        chart = DayChart()
        for limit in (0, 2):
            chart.set_data(days, limit)
            paint(chart, 380, 62)
        chart.set_data([(d, t, 0.0) for d, t, _c in days], 5)   # sem custo: usa tokens
        paint(chart, 380, 62)
        chart.set_data([], 0)
        paint(chart, 380, 62)
        chart.set_data(days, 0)
        self.assertIn("US$", chart.get_tooltip_text())

    def test_cost_chip_turns_red_over_the_limit(self):
        from views import Compact
        c = Compact()
        c.set_cost("US$ 9.00", over=True)
        self.assertTrue(c.cost_label.get_style_context().has_class("over"))
        c.set_cost("US$ 1.00")
        self.assertFalse(c.cost_label.get_style_context().has_class("over"))

    def test_session_row_has_terminal_button(self):
        from sessions_view import SessionRow
        row = SessionRow()
        row.set({"cwd": "/tmp", "pid": 123, "project": "p", "status": "busy", "since": 0,
                 "prompt": "oi", "title": None, "name": "n"})
        self.assertEqual(row.pid, 123)

    def test_settings_window_has_working_custom_controls(self):
        import config
        from gi.repository import Gdk
        from settings import Settings, settings_css
        with tempfile.TemporaryDirectory() as d:
            old, config.PATH = config.PATH, os.path.join(d, "c.json")  # não toca no config real
            try:
                cfg = config.Config()
            finally:
                config.PATH = old

        class Quiet(Settings):
            def show_all(self):
                pass

        win = Quiet(cfg)
        self.assertFalse(win.get_titlebar().get_show_close_button())  # nada de botões do tema
        self.assertEqual(win._max_glyph.name, "win_max")
        class Ev:  # evento de janela maximizada
            new_window_state = Gdk.WindowState.MAXIMIZED
        win._on_window_state(win, Ev)
        self.assertEqual(win._max_glyph.name, "win_restore")
        # o CSS gerado precisa ser aceito pelo GTK 3 (uma propriedade inválida impediria abrir)
        provider = Gtk.CssProvider()
        provider.load_from_data(settings_css(cfg).encode())

    def test_theme_group_saves_lists_and_deletes(self):
        import config
        import themes
        from settings import Settings
        with tempfile.TemporaryDirectory() as d:
            old_cfg, config.PATH = config.PATH, os.path.join(d, "c.json")
            old_dir, themes.USER_DIR = themes.USER_DIR, os.path.join(d, "themes")
            try:
                cfg = config.Config()

                class Quiet(Settings):
                    def show_all(self):
                        pass

                win = Quiet(cfg)
                self.assertEqual(len(win._theme_flow.get_children()), len(themes.BUILTIN))
                self.assertIn("Clássico", win._theme_status.get_text())     # o padrão é o Clássico
                cfg.set("bg_color", "rgb(5,6,7)")
                self.assertIn("personalizado", win._theme_status.get_text())
                themes.apply(cfg, themes.BUILTIN[2])                          # Claro
                self.assertIn("Claro", win._theme_status.get_text())
                win._theme_entry.set_text("Meu")
                win._save_theme()
                self.assertEqual(len(win._theme_flow.get_children()), len(themes.BUILTIN) + 1)
                win._theme_entry.set_text("claro")          # nome de tema embutido: recusa
                win._save_theme()
                self.assertEqual(len(themes.user_themes()), 1)
                themes.delete_user(themes.user_themes()[0])
                win._themes_changed()
                self.assertEqual(len(win._theme_flow.get_children()), len(themes.BUILTIN))
            finally:
                config.PATH, themes.USER_DIR = old_cfg, old_dir

    def test_auto_theme_and_kde_accent_controls(self):
        import config
        import themes
        from settings import Settings
        with tempfile.TemporaryDirectory() as d:
            old_cfg, config.PATH = config.PATH, os.path.join(d, "c.json")
            old_dir, themes.USER_DIR = themes.USER_DIR, os.path.join(d, "themes")
            try:
                cfg = config.Config()

                class Quiet(Settings):
                    def show_all(self):
                        pass

                win = Quiet(cfg)
                self.assertEqual(len(win._theme_combos), 2)
                combo = win._theme_combos[0][0]
                self.assertEqual(combo.get_active_id(), "Claro")
                # salvar um tema novo repovoa as listas sem mexer na configuração
                win._theme_entry.set_text("Novo")
                win._save_theme()
                self.assertEqual(cfg["theme_light"], "Claro")
                self.assertIn("Novo", [r[1] for r in combo.get_model()] + [r[0] for r in combo.get_model()])
                cfg.set("accent_follow_kde", True)       # o CSS das configurações continua válido
                provider = Gtk.CssProvider()
                from settings import settings_css
                provider.load_from_data(settings_css(cfg).encode())
            finally:
                config.PATH, themes.USER_DIR = old_cfg, old_dir

    def test_privacy_icons_show_hide_and_draw(self):
        from icons import Glyph
        from views import Compact
        c = Compact()
        c.set_privacy(["Firefox"], [])
        self.assertTrue(c.mic_rev.get_reveal_child())
        self.assertFalse(c.cam_rev.get_reveal_child())
        self.assertIn("Firefox", c.mic_rev.get_tooltip_text())
        c.set_privacy([], ["zoom", "chrome"])
        self.assertFalse(c.mic_rev.get_reveal_child())
        self.assertIn("zoom, chrome", c.cam_rev.get_tooltip_text())
        c.set_privacy([], [])
        self.assertFalse(c.cam_rev.get_reveal_child())
        for name in ("mic", "camera"):
            paint(Glyph(name, 14), 14, 14)

    def test_camera_page_states_without_opening_the_camera(self):
        import camtest
        from camera_view import CameraPage
        page = CameraPage()
        paint(page.preview, 384, 216)                      # aviso "câmera desligada"
        for db in (camtest.FLOOR_DB, -40.0, -10.0, 0.0):
            page._on_level(db)
            paint(page.level, 300, 12)
        page._on_frame(bytes(384 * 216 * 4), 384, 216)     # um quadro preto de mentira
        paint(page.preview, 384, 216)
        page._on_cam_error("erro de teste")
        self.assertIn("erro de teste", page.status.get_text())
        self.assertFalse(page.camera.running or page.mic.running)
        page.stop_all()                                    # seguro mesmo com tudo parado

    def test_bluetooth_page_for_every_state(self):
        from bluetooth_view import BluetoothPage

        class Fake:
            adapter, devices, busy = None, [], set()

            def toggle_device(self, d):
                self.last = d

            def set_powered(self, on):
                self.powered = on

        bt = Fake()
        page = BluetoothPage(bt)
        self.assertIn("adaptador", page.empty.get_text())
        self.assertFalse(page.power.get_sensitive())
        bt.adapter = {"path": "/a", "powered": False, "name": "x"}
        page.update()
        self.assertIn("desligado", page.empty.get_text())
        bt.adapter["powered"] = True
        page.update()
        self.assertIn("pareado", page.empty.get_text())
        bt.devices = [
            {"path": "/d1", "name": "Fone", "icon": "audio-headphones", "connected": True, "battery": 15},
            {"path": "/d2", "name": "Teclado", "icon": "input-keyboard", "connected": False, "battery": None}]
        bt.busy = {"/d2"}
        page.update()
        rows = page.listbox.get_children()
        self.assertEqual(len(rows), 2)
        self.assertEqual(page.power.get_label(), "Ligado")
        page.power.clicked()                      # alterna o adaptador pelo botão
        self.assertFalse(bt.powered)
        page.show_error("falhou")
        self.assertEqual(page.error.get_text(), "falhou")

    def test_generated_island_css_is_valid_for_every_builtin_theme(self):
        """Uma propriedade que o GTK 3 não conhece faria o CSS inteiro falhar ao carregar."""
        import config
        import themes
        for theme in themes.BUILTIN:
            cfg = make_cfg()
            cfg.update(theme["values"])
            provider = Gtk.CssProvider()
            errors = []
            provider.connect("parsing-error", lambda _p, _s, e: errors.append(e.message))
            provider.load_from_data(config.build_css(cfg).encode())
            self.assertEqual(errors, [], theme["name"])

    def test_system_page_builds_and_ticks(self):
        from system_view import SystemPage
        page = SystemPage(make_cfg())
        page._tick()           # leituras reais de rede/áudio, sem derrubar nada
        page._tick()
        page.set_fg((1, 1, 1))
        page.set_accent((0.2, 0.6, 0.9))
        page._got_audio((0.5, False))
        page._got_audio((0.5, True))
        page._got_audio(None)
        page._got_sinks([("a", "Alto-falante"), ("b", "Fone")], "a")
        page._got_connection(("wifi", "Casa", True))
        page._got_connection(("none", "", False))


if __name__ == "__main__":
    unittest.main()
