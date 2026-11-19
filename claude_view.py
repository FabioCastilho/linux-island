"""Página "Claude Code" da ilha expandida: uso de tokens por função, projeto e modelo."""
import threading

import gi

gi.require_version("PangoCairo", "1.0")
from gi.repository import GLib, Gtk, Pango, PangoCairo  # noqa: E402

import palette
from claude_usage import UsageStore, fmt_tokens, pretty_model
from i18n import _, short_date, weekday
from views import label
from widgets import Tweened, rounded_rect

PERIODS = (("Hoje", 1), ("7 dias", 7), ("30 dias", 30))
TABS = (("Funções", "tool"), ("Projetos", "project"), ("Modelos", "model"))
ROWS = 6


class Bar(Tweened, Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self._tween_init()
        self.fg = (1, 1, 1)
        self.set_size_request(-1, 6)
        self.set_hexpand(True)
        self.set_valign(Gtk.Align.CENTER)
        self.connect("draw", self._draw)

    def _draw(self, _w, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        cr.set_source_rgba(*self.fg, 0.12)
        rounded_rect(cr, 0, 0, w, h, h / 2)
        cr.fill()
        if self.fraction > 0:
            cr.set_source_rgb(*palette.CLAUDE)
            rounded_rect(cr, 0, 0, max(h, w * self.fraction), h, h / 2)
            cr.fill()


class Row(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        top = Gtk.Box(spacing=8)
        self.name = label("small", 0.0, True)
        self.value = label("dim small", 1.0)
        top.pack_start(self.name, True, True, 0)
        top.pack_end(self.value, False, False, 0)
        self.bar = Bar()
        self.pack_start(top, False, False, 0)
        self.pack_start(self.bar, False, False, 0)

    def set(self, name, tokens, frac):
        self.name.set_text(name)
        self.value.set_text(f"{fmt_tokens(tokens)}  ·  {round(frac * 100)}%")
        self.bar.set_fraction(frac)


def segmented(items, on_pick):
    box = Gtk.Box(spacing=4)
    buttons = {}
    for text, key in items:
        b = Gtk.Button(label=_(text))
        b.set_can_focus(False)
        b.get_style_context().add_class("seg")
        b.connect("clicked", lambda _b, k=key: on_pick(k))
        box.pack_start(b, False, False, 0)
        buttons[key] = b
    return box, buttons


def mark(buttons, active):
    for k, b in buttons.items():
        ctx = b.get_style_context()
        (ctx.add_class if k == active else ctx.remove_class)("active")




class DayChart(Gtk.DrawingArea):
    """Barras dos últimos dias (custo; se não houver custo, tokens), com a linha do limite."""

    HEIGHT = 62

    def __init__(self):
        super().__init__()
        self.data, self.limit = [], 0
        self.set_size_request(-1, self.HEIGHT)
        self.set_hexpand(True)
        self.connect("draw", self._draw)

    def set_data(self, data, limit):
        self.data, self.limit = data, limit
        self.set_tooltip_text("\n".join(
            f"{short_date(d)}: " + (f"US$ {c:.2f} · " if c >= 0.01 else "") + fmt_tokens(t)
            for d, t, c in data) or None)
        self.queue_draw()

    def _draw(self, _w, cr):
        if not self.data:
            return
        w, h = self.get_allocated_width(), self.get_allocated_height()
        c = self.get_style_context().get_color(self.get_state_flags())
        fg = (c.red, c.green, c.blue)
        use_cost = any(cost >= 0.01 for _d, _t, cost in self.data)
        vals = [cost if use_cost else tok for _d, tok, cost in self.data]
        limit = self.limit if use_cost else 0
        top = max(max(vals), limit, 1e-9)
        area = h - 16
        slot = w / len(self.data)
        bw = min(30, slot * 0.55)
        layout = self.create_pango_layout("")
        desc = Pango.FontDescription()
        desc.set_size(8 * Pango.SCALE)
        layout.set_font_description(desc)
        for i, ((day, _tok, cost), v) in enumerate(zip(self.data, vals)):
            x = i * slot + (slot - bw) / 2
            bh = max(2.0, area * v / top) if v > 0 else 2.0
            today = i == len(self.data) - 1
            if limit and cost >= limit:
                cr.set_source_rgb(*palette.FOCUS)  # dia acima do limite
            elif v <= 0:
                cr.set_source_rgba(*fg, 0.14)
            else:
                cr.set_source_rgba(*palette.CLAUDE, 1.0 if today else 0.55)
            rounded_rect(cr, x, area - bh, bw, bh, 3)
            cr.fill()
            layout.set_text(weekday(day.weekday(), True)[:3])
            tw = layout.get_pixel_size()[0]
            cr.set_source_rgba(*fg, 0.85 if today else 0.5)
            cr.move_to(i * slot + (slot - tw) / 2, area + 3)
            PangoCairo.show_layout(cr, layout)
        if limit:  # linha tracejada no valor do limite
            y = area * (1 - limit / top)
            cr.set_source_rgba(*palette.FOCUS, 0.9)
            cr.set_line_width(1.0)
            cr.set_dash([4, 3])
            cr.move_to(0, y)
            cr.line_to(w, y)
            cr.stroke()
            cr.set_dash([])


class ClaudePage(Gtk.Box):
    WIDTH = 420

    def __init__(self, cfg=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.cfg = cfg
        self.store = UsageStore()
        self.days, self.tab = 1, "tool"
        self._timer = None
        self._busy = False
        self._last = None
        self.set_size_request(self.WIDTH, -1)
        for side in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{side}")(18 if side in ("start", "end") else 14)

        head = Gtk.Box(spacing=8)
        title = label("title")
        title.set_text("Claude Code")
        head.pack_start(title, False, False, 0)
        period_box, self.period_btns = segmented(PERIODS, self._set_days)
        head.pack_end(period_box, False, False, 0)
        self.pack_start(head, False, False, 0)

        big = Gtk.Box(spacing=14)
        self.total = label("big-temp")
        self.total_sub = label("dim small")
        self.total_sub.set_valign(Gtk.Align.END)
        self.total_sub.set_margin_bottom(5)
        big.pack_start(self.total, False, False, 0)
        big.pack_start(self.total_sub, True, True, 0)
        self.pack_start(big, False, False, 0)

        cap = label("dim small")
        cap.set_text(_("Últimos 7 dias"))
        self.chart = DayChart()
        chart_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        chart_box.pack_start(cap, False, False, 0)
        chart_box.pack_start(self.chart, False, False, 0)
        self.pack_start(chart_box, False, False, 0)

        tabs, self.tab_btns = segmented(TABS, self._set_tab)
        self.pack_start(tabs, False, False, 0)

        self.rows = [Row() for _i in range(ROWS + 1)]
        rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        for r in self.rows:
            rows_box.pack_start(r, False, False, 0)
        rows_box.set_size_request(-1, 7 * 31)  # altura fixa: a ilha não "pula" ao trocar a aba
        self.pack_start(rows_box, False, False, 0)

        self.foot = label("dim small")
        self.pack_start(self.foot, False, False, 0)
        mark(self.period_btns, self.days)
        mark(self.tab_btns, self.tab)

        self.connect("map", self._start)
        self.connect("unmap", self._stop)

    def set_fg(self, fg):
        for r in self.rows:
            r.bar.fg = fg
            r.bar.queue_draw()

    # --- atualização -------------------------------------------------------
    def _start(self, *_a):
        self._render()  # mostra já o que está em cache
        self._reload()
        if self._timer is None:
            self._timer = GLib.timeout_add_seconds(15, self._reload)

    def _stop(self, *_a):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _reload(self):
        if self._busy:
            return True
        self._busy = True

        def work():
            self.store.refresh()
            GLib.idle_add(self._done)

        threading.Thread(target=work, daemon=True).start()
        return True

    def _done(self):
        self._busy = False
        self._render()
        return False

    def _set_days(self, d):
        self.days = d
        mark(self.period_btns, d)
        self._render()

    def _set_tab(self, t):
        self.tab = t
        mark(self.tab_btns, t)
        self._render()

    def refresh_limit(self):
        """O limite diário mudou nas configurações: redesenha a linha do gráfico."""
        self._render()

    def _render(self):
        limit = self.cfg["claude_daily_limit"] if self.cfg is not None else 0
        self.chart.set_data(self.store.daily(7), limit)
        s = self.store.summary(self.days)
        self.total.set_text(fmt_tokens(s["total"]))
        cost = f"  ·  ≈ US$ {s['cost']:.2f}" if s["cost"] >= 0.01 else ""
        self.total_sub.set_text(_("tokens{c}").format(c=cost))
        items = s[self.tab]
        for i, row in enumerate(self.rows):
            if i < len(items):
                name, tokens, frac = items[i]
                if self.tab == "model":
                    name = pretty_model(name)
                elif name == "(resposta)":
                    name = _("(resposta sem ferramenta)")
                row.set(name, tokens, frac)
                row.show()
            else:
                row.hide()
        self.foot.set_text(_("entrada {i}  ·  saída {o}  ·  cache lido {c}  ·  {m} msgs").format(
            i=fmt_tokens(s["in"]), o=fmt_tokens(s["out"]), c=fmt_tokens(s["cache_read"]),
            m=s["messages"]))
