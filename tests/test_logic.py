"""Testes da lógica pura da ilha (sem janela): rodar com `python3 -m unittest discover tests`."""
import json
import os
import tempfile
import unittest

import _path  # noqa: F401
import config
import pagelist
import sysinfo
from focus import Focus, fmt
from notif_history import NotificationHistory
import claude_usage
import terminal_focus
import themes
import kde
import privacy
import bluetooth
import camtest
import pagelist
import array
import autotheme
from datetime import datetime
from tasks import Tasks


class FakeNotification:
    def __init__(self, app="app", summary="s", body="b"):
        self.app, self.summary, self.body = app, summary, body


class ConfigTests(unittest.TestCase):
    def test_every_default_passes_its_own_validator(self):
        for key, (default, valid) in config.SCHEMA.items():
            self.assertTrue(valid(default), f"padrão inválido em {key}: {default!r}")

    def test_invalid_values_fall_back_and_valid_ones_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            with open(path, "w") as f:
                json.dump({"radius_expanded": 9999, "eq_style": "wave", "animations": "lol",
                           "pages_order": "tasks,tasks", "desconhecida": 1}, f)
            old, config.PATH = config.PATH, path
            try:
                cfg = config.Config()
            finally:
                config.PATH = old
        self.assertEqual(cfg["radius_expanded"], 30)       # fora da faixa: padrão
        self.assertEqual(cfg["eq_style"], "wave")          # válido: vale
        self.assertEqual(cfg["animations"], "normal")      # escolha inexistente: padrão
        self.assertEqual(cfg["pages_order"], "")           # página repetida: padrão

    def test_set_notifies_listeners_and_rejects_bad_values(self):
        with tempfile.TemporaryDirectory() as d:
            old, config.PATH = config.PATH, os.path.join(d, "c.json")
            try:
                cfg = config.Config()
                seen = []
                cfg.connect(seen.append)
                cfg.set("pomo_focus_min", 50)
                cfg.set("pomo_focus_min", 50)  # igual: não avisa de novo
                with self.assertRaises(ValueError):
                    cfg.set("pomo_focus_min", 0)
            finally:
                config.PATH = old
        self.assertEqual(seen, ["pomo_focus_min"])


class PageListTests(unittest.TestCase):
    def test_default_order_has_every_page_once(self):
        self.assertEqual(pagelist.order(""), list(pagelist.ALL_PAGES))

    def test_custom_order_goes_first_then_the_rest(self):
        o = pagelist.order("tasks,home")
        self.assertEqual(o[:2], ["tasks", "home"])
        self.assertEqual(sorted(o), sorted(pagelist.ALL_PAGES))

    def test_home_cannot_be_hidden(self):
        v = pagelist.visible("", "home,water")
        self.assertIn("home", v)
        self.assertNotIn("water", v)

    def test_move_clamps_at_the_edges(self):
        first = pagelist.order("")[0]
        self.assertEqual(pagelist.order(pagelist.move("", first, -1)), pagelist.order(""))
        self.assertEqual(pagelist.order(pagelist.move("", "home", 1))[1], "home")

    def test_spec_validation(self):
        self.assertTrue(pagelist.valid_spec(""))
        self.assertTrue(pagelist.valid_spec("home,tasks"))
        self.assertFalse(pagelist.valid_spec("home,home"))
        self.assertFalse(pagelist.valid_spec("nao-existe"))
        self.assertFalse(pagelist.valid_spec(3))


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FocusTests(unittest.TestCase):
    def make(self, **over):
        cfg = {"pomo_focus_min": 25, "pomo_short_min": 5, "pomo_long_min": 15, "pomo_rounds": 4,
               "pomo_auto_next": False}
        cfg.update(over)
        self.clock, self.events, self.done = FakeClock(), [], []
        return Focus(cfg, lambda: self.events.append(1), lambda a, b: self.done.append((a, b)),
                     self.clock)

    def test_runs_and_finishes_into_a_short_break(self):
        f = self.make()
        f.start()
        self.clock.t += 25 * 60 - 1
        self.assertFalse(f.tick())
        self.clock.t += 2
        self.assertTrue(f.tick())
        self.assertEqual(self.done, [("focus", "short")])
        self.assertEqual((f.phase, f.running, f.done_focus), ("short", False, 1))

    def test_fourth_focus_leads_to_the_long_break(self):
        f = self.make()
        for _i in range(4):
            f.set_phase("focus", start=True)
            self.clock.t += 25 * 60 + 1
            f.tick()
        self.assertEqual(self.done[-1], ("focus", "long"))
        self.assertEqual(f.round_in_cycle, 0)

    def test_skipping_a_focus_is_not_counted_and_never_goes_long(self):
        f = self.make()
        f.done_focus = 4  # ciclo recém-completo; o próximo foco foi pulado
        f.skip()
        self.assertEqual((f.phase, f.done_focus), ("short", 4))

    def test_pause_keeps_the_remaining_time(self):
        f = self.make()
        f.start()
        self.clock.t += 60
        f.pause()
        left = f.remaining
        self.clock.t += 500
        self.assertEqual(f.remaining, left)
        self.assertAlmostEqual(left, 24 * 60, delta=1)
        f.start()
        self.assertTrue(f.running)

    def test_auto_next_starts_the_following_phase(self):
        f = self.make(pomo_auto_next=True)
        f.start()
        self.clock.t += 25 * 60 + 1
        f.tick()
        self.assertTrue(f.running)
        self.assertEqual(f.phase, "short")

    def test_timer_mode_adjusts_only_when_stopped(self):
        f = self.make()
        f.set_phase("timer")
        f.adjust_timer(5)
        self.assertEqual(f.total, 15 * 60)
        f.start()
        f.adjust_timer(5)
        self.assertEqual(f.total, 15 * 60)
        f.pause()
        f.set_phase("focus")
        f.adjust_timer(5)  # fora do modo timer não faz nada
        self.assertEqual(f.total, 25 * 60)

    def test_fraction_and_format(self):
        f = self.make()
        self.assertEqual(f.fraction, 1.0)
        f.start()
        self.clock.t += 25 * 30
        self.assertAlmostEqual(f.fraction, 0.5, places=2)
        self.assertEqual(fmt(0), "0:00")
        self.assertEqual(fmt(59.2), "1:00")
        self.assertEqual(fmt(61), "1:01")


class HistoryTests(unittest.TestCase):
    def test_newest_first_trimmed_and_deduplicated(self):
        t = [0.0]
        h = NotificationHistory(max_items=3, clock=lambda: t[0])
        self.assertTrue(h.add(FakeNotification(summary="a")))
        self.assertFalse(h.add(FakeNotification(summary="a")))   # repetida em seguida
        t[0] = 10
        self.assertTrue(h.add(FakeNotification(summary="a")))    # passou da janela: conta
        for s in "bcd":
            t[0] += 10
            h.add(FakeNotification(summary=s))
        self.assertEqual([e.n.summary for e in h.items], ["d", "c", "b"])

    def test_unread_and_clear(self):
        h = NotificationHistory()
        calls = []
        h.connect(lambda: calls.append(1))
        h.add(FakeNotification())
        self.assertEqual(h.unread, 1)
        h.mark_read()
        self.assertEqual(h.unread, 0)
        h.clear()
        self.assertEqual(h.items, [])
        self.assertEqual(len(calls), 3)


class TasksTests(unittest.TestCase):
    def test_add_toggle_remove_and_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.json")
            t = Tasks(path)
            self.assertFalse(t.add("   "))
            self.assertTrue(t.add("  comprar   pão  "))
            self.assertTrue(t.add("ligar"))
            self.assertEqual([x["text"] for x in t.items], ["ligar", "comprar pão"])
            t.toggle(t.items[0]["id"])
            self.assertEqual(t.pending, 1)
            again = Tasks(path)  # relê do disco
            self.assertEqual([(x["text"], x["done"]) for x in again.items],
                             [("ligar", True), ("comprar pão", False)])
            again.clear_done()
            again.remove(again.items[0]["id"])
            self.assertEqual(again.items, [])

    def test_corrupt_file_starts_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.json")
            with open(path, "w") as f:
                f.write("{isso não é json")
            self.assertEqual(Tasks(path).items, [])

    def test_limits(self):
        with tempfile.TemporaryDirectory() as d:
            t = Tasks(os.path.join(d, "t.json"))
            t.add("x" * 500)
            self.assertEqual(len(t.items[0]["text"]), 200)


class SysInfoTests(unittest.TestCase):
    def test_wpctl_volume(self):
        self.assertEqual(sysinfo.parse_wpctl_volume("Volume: 0.45\n"), (0.45, False))
        self.assertEqual(sysinfo.parse_wpctl_volume("Volume: 0.30 [MUTED]"), (0.30, True))
        self.assertIsNone(sysinfo.parse_wpctl_volume("lixo"))
        self.assertIsNone(sysinfo.parse_wpctl_volume(None))

    def test_pactl_sinks(self):
        out = json.dumps([{"name": "a", "description": "Alto-falante"}, {"name": "b"}])
        self.assertEqual(sysinfo.parse_pactl_sinks(out), [("a", "Alto-falante"), ("b", "b")])
        self.assertEqual(sysinfo.parse_pactl_sinks("não é json"), [])

    def test_net_dev_ignores_virtual_interfaces(self):
        text = ("Inter-|   Receive\n face |bytes packets\n"
                "    lo: 100 1 0 0 0 0 0 0 100 1 0 0 0 0 0 0\n"
                " enp6s0: 5000 1 0 0 0 0 0 0 2000 1 0 0 0 0 0 0\n"
                "docker0: 900 1 0 0 0 0 0 0 900 1 0 0 0 0 0 0\n")
        stats = sysinfo.parse_net_dev(text)
        self.assertEqual(stats["enp6s0"], (5000, 2000))
        self.assertEqual(sysinfo.physical(stats), ["enp6s0"])

    def test_net_rate_and_counter_reset(self):
        r = sysinfo.NetRate()
        self.assertEqual(r.update((1000, 500), 0.0), (0.0, 0.0))
        self.assertEqual(r.update((3000, 700), 2.0), (1000.0, 100.0))
        self.assertEqual(r.update((10, 10), 3.0), (0.0, 0.0))  # contador voltou atrás
        self.assertIsNone(r.update(None, 4.0))

    def test_fmt_rate(self):
        self.assertEqual(sysinfo.fmt_rate(512), "512 B/s")
        self.assertEqual(sysinfo.fmt_rate(1500), "1.5 KB/s")
        self.assertEqual(sysinfo.fmt_rate(25_000_000), "25 MB/s")

    def test_nmcli_parsing_with_escaped_colons(self):
        rows = sysinfo.parse_nmcli_active("ethernet:Wired\\: casa:enp6s0\nvpn:Trabalho:wg0\n")
        self.assertEqual(rows[0], ("ethernet", "Wired: casa", "enp6s0"))
        self.assertEqual(sysinfo.describe_connection(rows), ("ethernet", "Wired: casa", True))
        self.assertEqual(sysinfo.describe_connection([]), ("none", "", False))
        wifi = [("802-11-wireless", "Casa", "wlan0")]
        self.assertEqual(sysinfo.describe_connection(wifi), ("wifi", "Casa", False))

    @staticmethod
    def write(path, text):
        with open(path, "w") as f:
            f.write(text)

    def test_battery_and_backlight_absent_on_desktops(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(sysinfo.read_battery(d))
            self.assertIsNone(sysinfo.read_backlight(d))

    def test_battery_and_backlight_present(self):
        with tempfile.TemporaryDirectory() as d:
            bat = os.path.join(d, "BAT0")
            os.makedirs(bat)
            self.write(os.path.join(bat, "capacity"), "87\n")
            self.write(os.path.join(bat, "status"), "Charging\n")
            self.assertEqual(sysinfo.read_battery(d), (87, True))
            bl = os.path.join(d, "intel_backlight")
            os.makedirs(bl)
            self.write(os.path.join(bl, "brightness"), "50\n")
            self.write(os.path.join(bl, "max_brightness"), "200\n")
            self.assertEqual(sysinfo.read_backlight(d), ("intel_backlight", 50, 200))


class ProjectNameTests(unittest.TestCase):
    def test_home_prefix_works_for_any_user(self):
        f = claude_usage.project_name
        self.assertEqual(f("-home-ana-meu-app", "/home/ana"), "meu/app")
        self.assertEqual(f("-home-ana", "/home/ana"), "~")                  # a própria home
        self.assertEqual(f("-home-joao-silva-site", "/home/joao.silva"), "site")
        self.assertEqual(f("-srv-outro-projeto", "/home/ana"), "/srv-outro-projeto")  # fora da home: sem prefixo para tirar


class DailyUsageTests(unittest.TestCase):
    def make_store(self, events, sessions):
        with tempfile.TemporaryDirectory() as d:
            old, claude_usage.CACHE = claude_usage.CACHE, os.path.join(d, "none.json")
            try:
                store = claude_usage.UsageStore()
            finally:
                claude_usage.CACHE = old
        store.events, store.sessions = events, sessions
        return store

    def test_daily_buckets_by_day_and_splits_session_cost(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).timestamp()
        ev = lambda t, sid, tok: {"t": t, "p": "p", "m": "m", "u": [tok, 0, 999, 0],  # noqa: E731
                                  "tools": [], "s": sid}
        # a sessão A gastou US$ 4 no total: 100 tokens ontem e 300 hoje
        store = self.make_store({"1": ev(yesterday, "A", 100), "2": ev(now.timestamp(), "A", 300)},
                                {"A": 4.0})
        days = store.daily(7)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1][0], now.date())
        self.assertEqual((days[-1][1], round(days[-1][2], 2)), (300, 3.0))   # cache lido fora
        self.assertEqual((days[-2][1], round(days[-2][2], 2)), (100, 1.0))
        self.assertEqual(days[0][1:], (0, 0.0))
        # bate com o resumo de hoje que a página já usa
        self.assertAlmostEqual(days[-1][2], store.summary(1)["cost"], places=6)

    def test_daily_ignores_events_older_than_the_window(self):
        from datetime import datetime, timedelta
        old = (datetime.now() - timedelta(days=30)).timestamp()
        store = self.make_store({"1": {"t": old, "p": "p", "m": "m", "u": [50, 0, 0, 0],
                                       "tools": [], "s": "A"}}, {"A": 1.0})
        self.assertTrue(all(t == 0 for _d, t, _c in store.daily(7)))


class TerminalFocusTests(unittest.TestCase):
    def test_parse_stat_handles_odd_process_names(self):
        self.assertEqual(terminal_focus.parse_stat("123 (konsole) S 77 1 1"), ("konsole", 77))
        self.assertEqual(terminal_focus.parse_stat("5 (a b) c) S 9 1"), ("a b) c", 9))
        self.assertIsNone(terminal_focus.parse_stat("lixo"))

    def test_ancestors_walk_a_fake_proc(self):
        with tempfile.TemporaryDirectory() as d:
            for pid, comm, ppid in ((300, "claude", 200), (200, "fish", 100),
                                    (100, "konsole", 50), (50, "systemd", 1)):
                os.makedirs(os.path.join(d, str(pid)))
                with open(os.path.join(d, str(pid), "stat"), "w") as f:
                    f.write(f"{pid} ({comm}) S {ppid} 1 1")
            self.assertEqual(terminal_focus.ancestors(300, d),
                             [(200, "fish"), (100, "konsole"), (50, "systemd")])
            self.assertEqual(terminal_focus.candidate_pids(300, d), [200, 100])  # sem systemd
            self.assertEqual(terminal_focus.candidate_pids(999, d), [])          # pid inexistente

    def test_script_only_contains_integers(self):
        js = terminal_focus.build_script([10, "20"])
        self.assertIn("var pids = [10, 20];", js)
        with self.assertRaises(ValueError):
            terminal_focus.build_script(["1; evil()"])


class ThemeTests(unittest.TestCase):
    def make_cfg(self, d):
        old, config.PATH = config.PATH, os.path.join(d, "c.json")
        try:
            return config.Config()
        finally:
            config.PATH = old

    def test_every_builtin_theme_is_valid_and_has_a_unique_name(self):
        names = [t["name"] for t in themes.BUILTIN]
        self.assertEqual(len(names), len(set(names)))
        for t in themes.BUILTIN:
            self.assertEqual(themes.clean_values(t["values"]), t["values"], t["name"])

    def test_slug_never_escapes_the_themes_folder(self):
        for bad in ("../../etc/passwd", "/abs/path", "a/b\\c", "..", "", "   ", "Tema Legal!"):
            s = themes.slug(bad)
            self.assertNotIn("/", s)
            self.assertNotIn("\\", s)
            self.assertNotIn("..", s)
            self.assertTrue(s)
        self.assertEqual(themes.slug("Tema Legal!"), "tema-legal")

    def test_invalid_values_and_unknown_keys_are_dropped(self):
        t = themes.parse_theme({"name": "x", "values": {
            "bg_color": "rgb(1,2,3)", "radius_expanded": 9999, "eq_style": "nope",
            "pages_order": "tasks", "notif_dnd": True}})
        self.assertEqual(t["values"], {"bg_color": "rgb(1,2,3)"})   # só chave de tema e válida
        self.assertIsNone(themes.parse_theme({"name": "", "values": {"bg_color": "rgb(1,2,3)"}}))
        self.assertIsNone(themes.parse_theme({"name": "x", "values": {"radius_expanded": 9999}}))
        self.assertIsNone(themes.parse_theme([1, 2]))

    def test_snapshot_save_reload_and_apply_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self.make_cfg(d)
            cfg.set("bg_color", "rgb(10,20,30)")
            cfg.set("notch_ear", 20)
            tdir = os.path.join(d, "themes")
            themes.save_user(themes.snapshot(cfg, "Meu Visual"), tdir)
            found = themes.user_themes(tdir)
            self.assertEqual([t["name"] for t in found], ["Meu Visual"])
            cfg.set("bg_color", "rgb(0,0,0)")
            cfg.set("notch_ear", 8)
            themes.apply(cfg, found[0])
            self.assertEqual((cfg["bg_color"], cfg["notch_ear"]), ("rgb(10,20,30)", 20))
            self.assertEqual(themes.active_name(cfg, found), "Meu Visual")
            cfg.set("notch_ear", 9)
            self.assertIsNone(themes.active_name(cfg, found))   # mexeu: virou personalizado

    def test_partial_theme_keeps_the_users_other_settings(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self.make_cfg(d)
            cfg.set("notch_style", True)
            cfg.set("notch_ear", 20)
            themes.apply(cfg, next(t for t in themes.BUILTIN if t["name"] == "Claro"))
            self.assertTrue(cfg["notch_style"])      # o tema Claro não desliga o seu entalhe
            self.assertEqual(cfg["notch_ear"], 20)
            self.assertEqual(cfg["bg_color"], "rgba(246,246,248,1)")

    def test_import_rejects_garbage_and_huge_files(self):
        with tempfile.TemporaryDirectory() as d:
            tdir = os.path.join(d, "themes")
            bad = os.path.join(d, "bad.json")
            with open(bad, "w") as f:
                f.write("isso não é json")
            self.assertIsNone(themes.import_from(bad, tdir))
            huge = os.path.join(d, "huge.json")
            with open(huge, "w") as f:
                f.write('{"name":"x","values":{"bg_color":"rgb(1,2,3)"},"pad":"' + "a" * 70000 + '"}')
            self.assertIsNone(themes.import_from(huge, tdir))
            good = os.path.join(d, "good.json")
            with open(good, "w") as f:
                json.dump({"name": "Bom", "values": {"bg_color": "rgb(1,2,3)"}}, f)
            self.assertEqual(themes.import_from(good, tdir)["name"], "Bom")
            self.assertEqual(len(themes.user_themes(tdir)), 1)

    def test_delete_only_touches_files_inside_the_themes_folder(self):
        with tempfile.TemporaryDirectory() as d:
            tdir = os.path.join(d, "themes")
            path = themes.save_user({"name": "A", "values": {"bg_color": "rgb(1,2,3)"}}, tdir)
            outside = os.path.join(d, "importante.json")
            with open(outside, "w") as f:
                f.write("{}")
            self.assertFalse(themes.delete_user({"file": outside}, tdir))   # fora da pasta
            self.assertTrue(os.path.exists(outside))
            self.assertFalse(themes.delete_user({"file": os.path.join(tdir, "..", "importante.json")}, tdir))
            self.assertTrue(themes.delete_user({"file": path}, tdir))
            self.assertFalse(os.path.exists(path))


KDE_DARK = """[General]
AccentColor=104,107,111
ColorScheme=Darkly

[Colors:Window]
BackgroundNormal=49,54,59

[Colors:Selection]
BackgroundNormal=61,174,233
"""
KDE_LIGHT = KDE_DARK.replace("49,54,59", "239,240,241").replace("Darkly", "BreezeLight")


class KdeTests(unittest.TestCase):
    def write(self, d, text):
        path = os.path.join(d, "kdeglobals")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_accent_dark_and_light_from_a_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d, KDE_DARK)
            self.assertEqual(kde.accent_spec(p), "rgb(104,107,111)")
            self.assertTrue(kde.is_dark(p))
            self.assertFalse(kde.is_dark(self.write(d, KDE_LIGHT)))

    def test_accent_falls_back_to_selection_color(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d, KDE_DARK.replace("AccentColor=104,107,111\n", ""))
            self.assertEqual(kde.accent_spec(p), "rgb(61,174,233)")

    def test_missing_or_broken_files_give_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(kde.accent(os.path.join(d, "nao-existe")))
            self.assertIsNone(kde.is_dark(os.path.join(d, "nao-existe")))
            p = self.write(d, "[General]\nAccentColor=999,1,1\n[Colors:Window]\nBackgroundNormal=lixo\n")
            self.assertIsNone(kde.accent(p))
            self.assertIsNone(kde.is_dark(p))


class AutoThemeTests(unittest.TestCase):
    def test_schedule_handles_midnight_wrap(self):
        f = autotheme.schedule_dark
        self.assertTrue(f(23, 19, 7))
        self.assertTrue(f(3, 19, 7))
        self.assertFalse(f(12, 19, 7))
        self.assertFalse(f(7, 19, 7))      # 7h já é claro
        self.assertTrue(f(19, 19, 7))      # 19h já é escuro
        self.assertTrue(f(22, 20, 23))     # sem atravessar a meia-noite
        self.assertFalse(f(10, 20, 23))
        self.assertFalse(f(5, 6, 6))       # início == fim: nunca escuro

    def test_decide(self):
        self.assertIsNone(autotheme.decide("off", True, 12, 19, 7))
        self.assertEqual(autotheme.decide("kde", True, 12, 19, 7), "dark")
        self.assertEqual(autotheme.decide("kde", False, 23, 19, 7), "light")
        self.assertIsNone(autotheme.decide("kde", None, 12, 19, 7))
        self.assertEqual(autotheme.decide("schedule", False, 23, 19, 7), "dark")

    def make(self, d, **over):
        old, config.PATH = config.PATH, os.path.join(d, "c.json")
        try:
            cfg = config.Config()
        finally:
            config.PATH = old
        for k, v in over.items():
            cfg.set(k, v)
        return cfg

    def test_applies_only_when_the_period_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "kdeglobals")
            with open(path, "w") as f:
                f.write(KDE_DARK)
            cfg = self.make(d, theme_auto="kde")
            auto = autotheme.AutoTheme(cfg, kde_path=path)
            self.assertEqual(auto.evaluate(force=True), "dark")
            self.assertEqual(cfg["bg_color"], "rgba(0,0,0,1)")            # Clássico
            cfg.set("bg_color", "rgb(9,9,9)")                             # o usuário ajusta
            self.assertIsNone(auto.evaluate())                            # mesmo período: respeita
            self.assertEqual(cfg["bg_color"], "rgb(9,9,9)")
            with open(path, "w") as f:
                f.write(KDE_LIGHT)
            self.assertEqual(auto.evaluate(), "light")                    # período mudou: troca
            self.assertEqual(cfg["bg_color"], "rgba(246,246,248,1)")      # Claro

    def test_off_mode_and_missing_theme_do_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self.make(d)
            self.assertIsNone(autotheme.AutoTheme(cfg).evaluate(force=True))   # modo desligado
            cfg = self.make(d, theme_auto="schedule", theme_dark="Não Existe")
            before = cfg["bg_color"]
            auto = autotheme.AutoTheme(cfg)
            self.assertIsNone(auto.evaluate(force=True, now=datetime(2026, 1, 1, 23)))
            self.assertEqual(cfg["bg_color"], before)

    def test_schedule_mode_uses_the_clock(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self.make(d, theme_auto="schedule")
            auto = autotheme.AutoTheme(cfg)
            self.assertEqual(auto.evaluate(now=datetime(2026, 1, 1, 12)), "light")
            self.assertEqual(cfg["bg_color"], "rgba(246,246,248,1)")
            self.assertEqual(auto.evaluate(now=datetime(2026, 1, 1, 21)), "dark")
            self.assertEqual(cfg["bg_color"], "rgba(0,0,0,1)")


def pw_node(cls, state, **props):
    return {"type": "PipeWire:Interface:Node",
            "info": {"state": state, "props": {"media.class": cls, **props}}}


class PrivacyTests(unittest.TestCase):
    def test_active_mic_and_camera_streams_are_reported(self):
        dump = json.dumps([
            pw_node("Stream/Input/Audio", "running", **{"application.name": "Firefox"}),
            pw_node("Stream/Input/Video", "running", **{"application.process.binary": "chrome"}),
        ])
        self.assertEqual(privacy.parse_pw_dump(dump), {"mic": ["Firefox"], "cam": ["chrome"]})

    def test_idle_monitor_and_peak_detect_streams_are_ignored(self):
        dump = json.dumps([
            pw_node("Stream/Input/Audio", "idle", **{"application.name": "Parado"}),
            pw_node("Stream/Input/Audio", "running", **{"application.name": "OBS",
                                                         "stream.capture.sink": True}),
            pw_node("Stream/Input/Audio", "running", **{"application.name": "plasmashell",
                                                         "media.name": "Peak detect"}),
            pw_node("Video/Source", "suspended", **{"node.name": "webcam"}),   # a câmera em si
            pw_node("Audio/Source", "running", **{"node.name": "mic"}),        # o dispositivo
            {"type": "PipeWire:Interface:Port"},
        ])
        self.assertEqual(privacy.parse_pw_dump(dump), {"mic": [], "cam": []})

    def test_garbage_input_is_safe(self):
        for bad in ("", "isso não é json", "null", '{"a": 1}', None):
            self.assertEqual(privacy.parse_pw_dump(bad), {"mic": [], "cam": []})

    def test_proc_scan_finds_direct_v4l2_users_but_not_pipewire(self):
        with tempfile.TemporaryDirectory() as d:
            for pid, comm, target in ((11, "zoom", "/dev/video0"), (12, "pipewire", "/dev/video0"),
                                      (13, "bash", "/dev/pts/3"), (14, "cheese", "/dev/video1")):
                fd = os.path.join(d, str(pid), "fd")
                os.makedirs(fd)
                os.symlink(target, os.path.join(fd, "5"))
                with open(os.path.join(d, str(pid), "comm"), "w") as f:
                    f.write(comm + "\n")
            os.makedirs(os.path.join(d, "self"))        # entradas não numéricas não contam
            self.assertEqual(sorted(privacy.scan_video_openers(d)), ["cheese", "zoom"])
            self.assertEqual(privacy.scan_video_openers(os.path.join(d, "nao-existe")), [])

    def test_unique_keeps_order(self):
        self.assertEqual(privacy.unique(["a", "b", "a", "c"]), ["a", "b", "c"])


class CamTestTests(unittest.TestCase):
    def pcm(self, values):
        return array.array("h", values).tobytes()

    def test_silence_and_full_scale(self):
        self.assertEqual(camtest.level_db(self.pcm([0] * 100)), camtest.FLOOR_DB)
        self.assertEqual(camtest.level_db(b""), camtest.FLOOR_DB)
        self.assertAlmostEqual(camtest.level_db(self.pcm([32767, -32767] * 50)), 0.0, places=1)

    def test_half_amplitude_is_about_minus_six_db(self):
        self.assertAlmostEqual(camtest.level_db(self.pcm([16384, -16384] * 50)), -6.0, delta=0.1)

    def test_fraction_maps_the_range_and_clamps(self):
        self.assertEqual(camtest.level_fraction(camtest.FLOOR_DB), 0.0)
        self.assertEqual(camtest.level_fraction(0.0), 1.0)
        self.assertAlmostEqual(camtest.level_fraction(-30.0), 0.5)
        self.assertEqual(camtest.level_fraction(-200.0), 0.0)
        self.assertEqual(camtest.level_fraction(12.0), 1.0)

    def test_every_video_pipeline_has_a_fixed_mode_and_the_same_output(self):
        self.assertGreaterEqual(len(camtest.VIDEO_PIPES), 3)   # tem alternativas de modo
        for text in camtest.VIDEO_PIPES:
            self.assertIn("width=", text.split("videoconvert")[0])      # fonte com modo concreto
            self.assertIn(f"width={camtest.VIDEO_W},height={camtest.VIDEO_H}", text)


def dbus_props(**kw):
    return kw


class BluetoothParseTests(unittest.TestCase):
    OBJS = {
        "/org/bluez/hci0": {"org.bluez.Adapter1": {"Powered": True, "Alias": "meu-pc"}},
        "/org/bluez/hci0/dev_A": {"org.bluez.Device1": {
            "Alias": "Fone Z", "Icon": "audio-headphones", "Paired": True, "Connected": True},
            "org.bluez.Battery1": {"Percentage": 72}},
        "/org/bluez/hci0/dev_B": {"org.bluez.Device1": {
            "Alias": "Teclado", "Icon": "input-keyboard", "Paired": True, "Connected": False}},
        "/org/bluez/hci0/dev_C": {"org.bluez.Device1": {      # só visto ao redor: não aparece
            "Alias": "TV da vizinha", "Paired": False, "Connected": False}},
        "/org/bluez/hci0/dev_D": {"org.bluez.Device1": {
            "Alias": "Alto-falante", "Paired": True, "Connected": True}},
    }

    def test_only_paired_or_connected_devices_connected_first(self):
        r = bluetooth.parse_objects(self.OBJS)
        self.assertEqual(r["adapter"], {"path": "/org/bluez/hci0", "powered": True,
                                        "name": "meu-pc"})
        self.assertEqual([d["name"] for d in r["devices"]], ["Alto-falante", "Fone Z", "Teclado"])
        phone = r["devices"][1]
        self.assertEqual((phone["connected"], phone["battery"], phone["icon"]),
                         (True, 72, "audio-headphones"))
        self.assertIsNone(r["devices"][0]["battery"])
        self.assertEqual(r["devices"][0]["icon"], "bluetooth")            # sem ícone informado

    def test_no_adapter_and_garbage_are_safe(self):
        for objs in ({}, None, {"/x": {"org.freedesktop.DBus.Properties": {}}}):
            r = bluetooth.parse_objects(objs)
            self.assertIsNone(r["adapter"])
            self.assertEqual(r["devices"], [])

    def test_new_pages_are_registered(self):
        self.assertIn("camera", pagelist.ALL_PAGES)
        self.assertIn("bluetooth", pagelist.ALL_PAGES)
        self.assertEqual(sorted(pagelist.order("")), sorted(pagelist.ALL_PAGES))



class AgendaCreateEventTests(unittest.TestCase):
    TODAY = datetime(2026, 11, 20).date()

    def test_parse_date_accepts_friendly_and_numeric_forms(self):
        import agenda
        d = self.TODAY
        self.assertEqual(agenda.parse_date("", d), d)
        self.assertEqual(agenda.parse_date("Amanhã", d), datetime(2026, 11, 21).date())
        self.assertEqual(agenda.parse_date("25/12", d), datetime(2026, 12, 25).date())
        self.assertEqual(agenda.parse_date("5/1/2027", d), datetime(2027, 1, 5).date())
        self.assertEqual(agenda.parse_date("2027-01-05", d), datetime(2027, 1, 5).date())

    def test_parse_date_rejects_garbage(self):
        import agenda
        for bad in ("31/02", "32/01/2026", "abc", "2026/01/01", "13-01"):
            with self.assertRaises(ValueError, msg=bad):
                agenda.parse_date(bad, self.TODAY)

    def test_parse_time(self):
        import agenda
        self.assertEqual(agenda.parse_time("14:30").hour, 14)
        self.assertEqual(agenda.parse_time("9h").hour, 9)
        self.assertEqual(agenda.parse_time("07").minute, 0)
        for bad in ("25:00", "12:60", "x", "", "12:3"):
            with self.assertRaises(ValueError, msg=bad):
                agenda.parse_time(bad)

    def test_build_event_timed_has_only_the_essentials(self):
        import agenda
        from datetime import time
        body = agenda.build_event("  Dentista ", self.TODAY, time(14, 0), 45)
        self.assertEqual(set(body), {"summary", "start", "end"})  # sem convidados/local/lembretes
        self.assertEqual(body["summary"], "Dentista")
        start = datetime.fromisoformat(body["start"]["dateTime"])
        end = datetime.fromisoformat(body["end"]["dateTime"])
        self.assertIsNotNone(start.tzinfo)
        self.assertEqual((end - start).total_seconds(), 45 * 60)

    def test_build_event_all_day_ends_next_day(self):
        import agenda
        body = agenda.build_event("Feriado", self.TODAY)
        self.assertEqual(body["start"], {"date": "2026-11-20"})
        self.assertEqual(body["end"], {"date": "2026-11-21"})

    def test_build_event_validates(self):
        import agenda
        from datetime import time
        for title, dur in (("", 60), ("   ", 60), ("x" * 201, 60), ("ok", 4), ("ok", 24 * 60 + 1)):
            with self.assertRaises(ValueError, msg=(title[:5], dur)):
                agenda.build_event(title, self.TODAY, time(10, 0), dur)

    def test_write_is_opt_in_by_default(self):
        self.assertIs(config.SCHEMA["agenda_write"][0], False)


class GoogleCalendarWriteTests(unittest.TestCase):
    def _gc(self, token):
        import google_calendar
        gc = object.__new__(google_calendar.GoogleCalendar)  # sem chaveiro nem rede
        gc.token = token
        return gc

    def test_can_write_depends_on_the_granted_scope(self):
        import google_calendar as g
        self.assertFalse(self._gc(None).can_write)
        self.assertFalse(self._gc({"refresh_token": "r"}).can_write)  # token antigo, sem scope
        self.assertFalse(self._gc({"refresh_token": "r", "scope": g.SCOPE_READ}).can_write)
        self.assertTrue(self._gc({"refresh_token": "r",
                                  "scope": f"{g.SCOPE_READ} {g.SCOPE_WRITE}"}).can_write)

    def test_create_event_refuses_without_write_scope(self):
        import google_calendar as g
        gc = self._gc({"refresh_token": "r", "scope": g.SCOPE_READ})
        with self.assertRaises(g.AuthError):
            gc.create_event({"summary": "x"})

    def test_client_can_only_create_never_edit_or_delete(self):
        import google_calendar as g
        public = {n for n in dir(g.GoogleCalendar) if not n.startswith("_")}
        for forbidden in ("update_event", "delete_event", "patch_event", "edit_event",
                          "remove_event", "move_event"):
            self.assertNotIn(forbidden, public)
        self.assertIn("create_event", public)


class BrandDetectionTests(unittest.TestCase):
    def test_url_wins_and_matches_subdomains(self):
        import brands
        self.assertEqual(brands.detect("x", "https://www.youtube.com/watch?v=1"), "youtube")
        self.assertEqual(brands.detect("x", "https://m.youtube.com/watch?v=1"), "youtube")
        self.assertEqual(brands.detect("x", "https://youtu.be/abc"), "youtube")
        self.assertEqual(brands.detect("x", "https://music.youtube.com/watch?v=1"), "youtube_music")
        self.assertEqual(brands.detect("x", "https://web.whatsapp.com/"), "whatsapp")

    def test_title_suffix_works_without_url(self):
        import brands
        self.assertEqual(brands.detect("Minha OPINIÃO sobre GTA 6 - YouTube", ""), "youtube")
        self.assertEqual(brands.detect("Lofi - YouTube Music", ""), "youtube_music")
        self.assertEqual(brands.detect("WhatsApp", ""), "whatsapp")

    def test_lookalike_domains_and_plain_music_are_not_brands(self):
        import brands
        for title, url in (("Música", ""), ("x", "https://notyoutube.com/a"),
                           ("x", "https://evil.com/youtube.com"), ("x", "https://youtube.com.evil.io/"),
                           ("Song", "https://open.spotify.com/track/1"), ("", ""), (None, None),
                           ("x", "http://[bad")):
            self.assertIsNone(brands.detect(title, url), (title, url))

    def test_music_services_are_detected_and_flagged_as_music(self):
        import brands
        self.assertEqual(brands.detect("x", "https://www.deezer.com/br/track/1"), "deezer")
        self.assertEqual(brands.detect("x", "https://music.apple.com/br/album/1"), "apple_music")
        self.assertEqual(brands.detect("Faixa - Deezer", ""), "deezer")
        for b in ("youtube_music", "deezer", "apple_music"):
            self.assertIn(b, brands.MUSIC)
        for b in ("youtube", "whatsapp", "twitch", "netflix", "telegram"):
            self.assertNotIn(b, brands.MUSIC)  # vídeo e chat: sempre a logo

    def test_every_brand_has_a_logo_and_a_color(self):
        import brands
        names = set(brands.DRAW)
        self.assertEqual(names, set(brands.COLORS))
        for _h, b in brands.HOSTS + brands.TITLE_SUFFIXES:
            self.assertIn(b, names)


if __name__ == "__main__":
    unittest.main()
