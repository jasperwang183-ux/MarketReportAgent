"""
generate_brief.py — Build the daily ETF research brief.

Loads data/snapshot.json + CLAUDE.md, computes the QQQ drawdown signal,
sends a structured prompt to Claude, prints the report to the terminal,
and saves to output/YYYY-MM-DD-brief.md.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import load_env  # noqa: F401 — pulls .env (ANTHROPIC_API_KEY etc.) into os.environ

PROJECT_DIR = Path(__file__).resolve().parent
SNAPSHOT_FILE = PROJECT_DIR / "data" / "snapshot.json"
HISTORY_DIR = PROJECT_DIR / "data" / "history"
SIGNAL_STATE_FILE = PROJECT_DIR / "data" / "signal_state.json"
CLAUDE_MD = PROJECT_DIR / "CLAUDE.md"
OUTPUT_DIR = PROJECT_DIR / "output"

# Kill signals the daily tier actually web-searches (fast-moving).
# All others are carried forward from the last weekly. Iran exit is handled
# separately (daily always searches it).
DAILY_SEARCHED_SIGNALS = {"KS-1", "KS-W"}

# KS-1..KS-W = memory thesis (Layer 2); AS-1 = ASIC substitution (Layer 1).
ALL_KILL_SIGNALS = ["KS-1", "KS-2", "KS-3", "KS-4", "KS-5", "KS-W", "AS-1"]

# KS-2 numeric guide tracking + earnings-day escalation scope.
HYPERSCALERS = ["MSFT", "GOOG", "AMZN", "META"]
# NVDA earnings drive AS-1 escalation the same way hyperscalers drive KS-2.
EARNINGS_WATCH = HYPERSCALERS + ["NVDA"]

# Consecutive-period kill conditions tracked NUMERICALLY. Their triggers are
# streaks ("-10% MoM x3 months"), which a carried-forward prose note can't
# verify. The model reports only the latest reading (value_key + period_key)
# in its JSON block; the script owns the per-period history and computes the
# streak deterministically — same philosophy as the script-computed TQQQ zone.
NUMERIC_STREAKS = {
    "KS-1": {"period_key": "month", "value_key": "mom_pct",
             "period_re": re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"),
             "threshold": -10.0, "needed": 3, "label": "DRAM spot MoM"},
    "KS-4": {"period_key": "quarter", "value_key": "qoq_pct",
             "period_re": re.compile(r"^\d{4}-Q[1-4]$"),
             "threshold": -10.0, "needed": 2, "label": "server DDR5 QoQ"},
    # AS-1 kill leg B: NVDA data-center revenue QoQ negative x2 consecutive.
    # (Leg A — YoY growth <20% — is carried in value/status by the model.)
    "AS-1": {"period_key": "quarter", "value_key": "qoq_pct",
             "period_re": re.compile(r"^\d{4}-Q[1-4]$"),
             "threshold": 0.0, "needed": 2, "label": "NVDA DC revenue QoQ"},
}


def _prev_period(period: str) -> str:
    """Predecessor of a 'YYYY-MM' month or 'YYYY-Qn' quarter label."""
    if "-Q" in period:
        y, q = period.split("-Q")
        y, q = int(y), int(q)
        return f"{y - 1}-Q4" if q == 1 else f"{y}-Q{q - 1}"
    y, m = period.split("-")
    y, m = int(y), int(m)
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _update_streak_history(entry: dict, mk: dict, spec: dict) -> None:
    """Upsert the model's latest numeric reading and recompute the streak.

    The streak counts calendar-CONSECUTIVE trailing periods at/below the
    threshold — a gap in the data breaks it, so missing months can't silently
    inflate progress toward a kill.
    """
    history = [h for h in entry.get("history", [])
               if isinstance(h, dict) and isinstance(h.get("period"), str)
               and isinstance(h.get("pct"), (int, float))]
    period = mk.get(spec["period_key"])
    pct = mk.get(spec["value_key"])
    if isinstance(period, str) and spec["period_re"].match(period) \
            and isinstance(pct, (int, float)) and not isinstance(pct, bool):
        history = [h for h in history if h["period"] != period]
        history.append({"period": period, "pct": round(float(pct), 2)})
        history.sort(key=lambda h: h["period"])
        history = history[-8:]
    entry["history"] = history

    streak, expect = 0, None
    for h in reversed(history):
        if expect is not None and h["period"] != expect:
            break
        if h["pct"] > spec["threshold"]:
            break
        streak += 1
        expect = _prev_period(h["period"])
    entry["streak"] = streak


_QTR_RE = re.compile(r"^\d{4}-Q[1-4]$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _update_capex_guides(entry: dict, mk: dict) -> None:
    """Upsert per-hyperscaler CapEx growth guides and count the kill condition.

    KS-2's kill is '2+ hyperscalers guide CapEx growth <10% same quarter' —
    a deterministic count once each name's latest guide % is on file, so the
    script owns it instead of the model re-judging from memory each run.
    """
    guides = {
        n: g for n, g in (entry.get("guides") or {}).items()
        if isinstance(g, dict) and isinstance(g.get("pct"), (int, float))
        and isinstance(g.get("quarter"), str)
    }
    model_guides = mk.get("guides")
    if isinstance(model_guides, dict):
        for name, g in model_guides.items():
            n = str(name).upper()
            if n not in HYPERSCALERS or not isinstance(g, dict):
                continue
            pct, qtr = g.get("pct"), g.get("quarter")
            if isinstance(pct, (int, float)) and not isinstance(pct, bool) \
                    and isinstance(qtr, str) and _QTR_RE.match(qtr):
                guides[n] = {"pct": round(float(pct), 1), "quarter": qtr}
    entry["guides"] = guides
    if guides:
        latest_q = max(g["quarter"] for g in guides.values())
        in_q = {n: g["pct"] for n, g in guides.items()
                if g["quarter"] == latest_q}
        entry["guide_quarter"] = latest_q
        entry["below_10"] = sorted(n for n, p in in_q.items() if p < 10)
        entry["warn_10_13"] = sorted(n for n, p in in_q.items() if 10 <= p <= 13)
    else:
        entry["guide_quarter"] = None
        entry["below_10"] = []
        entry["warn_10_13"] = []


def earnings_escalations(state: dict, today: str) -> list[str]:
    """EARNINGS_WATCH names whose stored earnings date is today or yesterday.

    Earnings land after the close, so the next morning's 6am daily run is the
    first chance to catch the guide — hence the 2-day window.
    """
    try:
        t = datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        return []
    due = []
    for name, d in (state.get("earnings_calendar") or {}).items():
        if name not in EARNINGS_WATCH or not isinstance(d, str):
            continue
        try:
            delta = (t - datetime.strptime(d, "%Y-%m-%d")).days
        except ValueError:
            continue
        if 0 <= delta <= 1:
            due.append(name)
    return sorted(due)

MODEL = "claude-opus-4-8"  # same $5/$25 pricing as 4.6; drop-in upgrade (adaptive
                           # thinking + _20260209 web tools already in use here)
# 4000 truncated the report mid-Section-7 (Sections 8/9 never rendered). The full
# 9-section brief + Potential Buys callout + adaptive-thinking tokens + room for
# web-search reasoning needs real headroom. We stream the call, so a large cap
# carries no HTTP-timeout risk.
MAX_TOKENS = 16000

# Server-side web tools (Opus 4.6+ / Sonnet 4.6+). The _20260209 versions run
# dynamic filtering automatically — no extra beta header or code_execution tool.
# This is what lets the agent actually perform the news/macro searches CLAUDE.md
# specifies (Iran/Hormuz, DRAM/HBM pricing, hyperscaler CapEx, semis) instead of
# reasoning from price action alone.
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209", "name": "web_fetch"},
]

# Cap on pause_turn resumptions (server tool loop hits its iteration limit).
MAX_CONTINUATIONS = 6


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_snapshot() -> dict:
    if not SNAPSHOT_FILE.exists():
        die(
            f"Snapshot not found at {SNAPSHOT_FILE.relative_to(PROJECT_DIR)}. "
            "Run `python fetch_data.py` first."
        )
    try:
        return json.loads(SNAPSHOT_FILE.read_text())
    except json.JSONDecodeError as exc:
        die(f"Could not parse {SNAPSHOT_FILE.name}: {exc}")


PORTFOLIO_MD = PROJECT_DIR / "portfolio.md"
PORTFOLIO_MARKER = "<!-- PORTFOLIO_MD -->"


def load_thesis() -> str:
    """CLAUDE.md with the gitignored portfolio.md spliced in.

    Positions are personal financial data, so they live outside the committed
    spec; the PORTFOLIO SNAPSHOT section in CLAUDE.md carries a marker that is
    replaced here so the model still sees one seamless document.
    """
    if not CLAUDE_MD.exists():
        die(f"CLAUDE.md not found at {CLAUDE_MD}.")
    thesis = CLAUDE_MD.read_text()
    if PORTFOLIO_MARKER in thesis:
        if not PORTFOLIO_MD.exists():
            die(
                "portfolio.md not found — it holds your positions and is "
                "required to generate a report. Copy portfolio.example.md to "
                "portfolio.md and fill in your holdings."
            )
        thesis = thesis.replace(PORTFOLIO_MARKER, PORTFOLIO_MD.read_text().strip())
    return thesis


def format_market_block(snap: dict) -> str:
    """Render the snapshot as a compact, model-friendly table."""
    lines = [
        f"Snapshot generated at: {snap.get('generated_at_utc', 'unknown')}",
        "",
        "Per-ticker readings:",
        "Ticker | Price | Day % | RSI(14) | Vol | 20d Avg Vol | 52w High | Last Bar | Notes",
    ]

    def fmt(x, d=2):
        return f"{x:,.{d}f}" if isinstance(x, (int, float)) else "—"

    def fmt_int(x):
        return f"{int(x):,}" if isinstance(x, (int, float)) else "—"

    def ticker_row(ticker, rec):
        notes_bits = []
        if rec.get("error"):
            notes_bits.append(f"ERR:{rec['error']}")
        if rec.get("stale"):
            notes_bits.append("STALE")
        notes = ", ".join(notes_bits) if notes_bits else "ok"
        return " | ".join([
            ticker,
            fmt(rec.get("price"), 2),
            fmt(rec.get("day_change_pct"), 2),
            fmt(rec.get("rsi_14"), 1),
            fmt_int(rec.get("volume")),
            fmt_int(rec.get("avg_volume_20d")),
            fmt(rec.get("high_52w"), 2),
            rec.get("last_bar_date") or "—",
            notes,
        ])

    for ticker, rec in snap.get("tickers", {}).items():
        lines.append(ticker_row(ticker, rec))

    watch = snap.get("watchlist", {})
    if watch:
        lines += [
            "",
            "Candidate / watchlist ETFs (NOT held — unowned, thesis-relevant):",
            "These are the pool for Section 4 gap-fills and the Potential Buys "
            "callout. Select/cycle which to highlight based on today's RSI, "
            "drawdown from 52w high, volume, and any catalyst.",
            "Ticker | Price | Day % | RSI(14) | Vol | 20d Avg Vol | 52w High | Last Bar | Notes",
        ]
        for ticker, rec in watch.items():
            lines.append(ticker_row(ticker, rec))

    dd = snap.get("qqq_drawdown", {})
    qqq_price = dd.get("qqq_price")
    qqq_high = dd.get("qqq_52w_high")
    drawdown = dd.get("drawdown_pct")

    lines += [
        "",
        "TQQQ Drawdown Signal (computed from QQQ vs 52-week high):",
        f"  QQQ price:    {fmt(qqq_price, 2)}",
        f"  QQQ 52w high: {fmt(qqq_high, 2)}",
        f"  Drawdown:     {fmt(drawdown, 2)}%",
    ]

    if drawdown is not None:
        if drawdown < 10:
            zone = "Below 10% — Near ATH. Favor QQQ (1x). Consider reducing TQQQ in IRA."
        elif drawdown < 20:
            zone = "10–20% — Real pullback. TQQQ appropriate. Hold or add in IRA."
        else:
            zone = "Above 20% — Deep correction. Full TQQQ conviction."
        lines.append(f"  Zone:         {zone}")

    vix = snap.get("vix", {})
    if vix.get("level") is not None:
        lines.append(
            f"  VIX (secondary signal): {fmt(vix['level'], 2)} | "
            f"Δ {fmt(vix.get('day_change'), 2)} vs prior close | "
            f"5d avg {fmt(vix.get('avg_5d'), 2)} | "
            f"direction: {vix.get('direction') or 'unknown'}"
        )
    else:
        lines.append(
            "  VIX (secondary signal): no fresh data"
            + (f" ({vix['error']})" if vix.get("error") else "")
            + " — say so rather than guessing a level"
        )

    if snap.get("errors"):
        lines.append("")
        lines.append(f"Errors on: {', '.join(snap['errors'])}")
    if snap.get("stale"):
        lines.append(f"Stale data: {', '.join(snap['stale'])}")

    return "\n".join(lines)


def snapshot_usable(snap: dict) -> bool:
    """True if at least one HELD ticker carries a numeric price.

    yfinance occasionally fails wholesale, producing an archive where every
    price is null (e.g. history/2026-06-08.json, 2026-06-15.json). Such a file
    is useless as a delta baseline — comparing against it renders every delta
    as "—" and silently kills the What Changed section.
    """
    return any(
        isinstance(rec, dict) and isinstance(rec.get("price"), (int, float))
        for rec in (snap.get("tickers") or {}).values()
    )


def load_prior_snapshot(current: dict) -> dict | None:
    """Most recent USABLE archived snapshot from a date strictly before today's.

    Returns None on the first-ever run (no prior archive). Used to compute the
    day-over-day delta block. Re-runs on the same day are skipped so we always
    compare against the previous *session*, not an earlier run of today.
    Poisoned archives (no usable prices) are skipped, walking back to the last
    good session — so the day after a failed fetch still gets real deltas.
    """
    if not HISTORY_DIR.exists():
        return None
    today = current.get("generated_at_utc", "")[:10]
    candidates = []
    for entry in HISTORY_DIR.glob("*.json"):
        stamp = entry.stem  # YYYY-MM-DD
        if len(stamp) == 10 and stamp < today:
            candidates.append((stamp, entry))
    candidates.sort(reverse=True)  # newest prior date first
    for stamp, path in candidates:
        try:
            snap = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            print(f"NOTE: skipping unreadable history snapshot {path.name}.",
                  file=sys.stderr)
            continue
        if not snapshot_usable(snap):
            print(f"NOTE: skipping poisoned history snapshot {path.name} "
                  "(no usable prices) — walking back to the last good one.",
                  file=sys.stderr)
            continue
        return snap
    return None


def format_delta_block(current: dict, prior: dict | None) -> str:
    """Render day-over-day changes vs the prior session for the model to narrate.

    Covers price %, RSI move, and distance-to-52w-high for held + watchlist
    tickers, plus the QQQ drawdown shift. Returns "" when there is no prior
    snapshot (first run) so the prompt can note that explicitly.
    """
    if not prior:
        return ""

    prior_date = prior.get("generated_at_utc", "unknown")[:10]
    cur_date = current.get("generated_at_utc", "unknown")[:10]

    def pct_off_high(rec):
        p, h = rec.get("price"), rec.get("high_52w")
        if isinstance(p, (int, float)) and isinstance(h, (int, float)) and h:
            return (h - p) / h * 100
        return None

    def fmt_signed(x, d=2, suffix=""):
        if not isinstance(x, (int, float)):
            return "—"
        return f"{x:+,.{d}f}{suffix}"

    lines = [
        f"Prior session archived: {prior_date}  →  current: {cur_date}",
        "(If the two dates' market bars match, markets were closed between runs "
        "— price deltas will be ~0; say so rather than implying movement.)",
        "",
        "Per-ticker change vs prior session:",
        "Ticker | Prev Px | Now Px | Px Δ% | RSI Δ | Now %off52wHi | Notes",
    ]

    def emit(label, names, store_key):
        lines.append(f"-- {label} --")
        cur_store = current.get(store_key, {})
        prior_store = prior.get(store_key, {})
        for t in names:
            c = cur_store.get(t)
            p = prior_store.get(t)
            if not c:
                continue
            if not p:
                lines.append(f"{t} | (new — no prior) | {c.get('price')} | — | — | — | new ticker")
                continue
            cp, pp = c.get("price"), p.get("price")
            px_chg = ((cp / pp - 1) * 100) if (isinstance(cp, (int, float))
                      and isinstance(pp, (int, float)) and pp) else None
            rsi_chg = ((c.get("rsi_14") - p.get("rsi_14"))
                       if isinstance(c.get("rsi_14"), (int, float))
                       and isinstance(p.get("rsi_14"), (int, float)) else None)
            off_hi = pct_off_high(c)
            lines.append(" | ".join([
                t,
                f"{pp:,.2f}" if isinstance(pp, (int, float)) else "—",
                f"{cp:,.2f}" if isinstance(cp, (int, float)) else "—",
                fmt_signed(px_chg, 2, "%"),
                fmt_signed(rsi_chg, 1),
                f"{off_hi:,.2f}%" if off_hi is not None else "—",
                "ok",
            ]))

    held = list(current.get("tickers", {}).keys())
    watch = list(current.get("watchlist", {}).keys())
    emit("HELD", held, "tickers")
    emit("WATCHLIST", watch, "watchlist")

    cdd = current.get("qqq_drawdown", {}).get("drawdown_pct")
    pdd = prior.get("qqq_drawdown", {}).get("drawdown_pct")
    if isinstance(cdd, (int, float)) and isinstance(pdd, (int, float)):
        lines += [
            "",
            f"QQQ drawdown: {pdd:.2f}% → {cdd:.2f}% "
            f"(Δ {cdd - pdd:+.2f} pts) — TQQQ signal drift.",
        ]

    # Surface data-quality changes (new errors/stale tickers vs prior).
    new_err = set(current.get("errors", [])) - set(prior.get("errors", []))
    if new_err:
        lines.append(f"NEW data errors since prior: {', '.join(sorted(new_err))}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Signal-state persistence (read / write / merge)
# ---------------------------------------------------------------------------

def _default_signal_state() -> dict:
    """Skeleton for the first-ever run (no signal_state.json on disk)."""
    sig = {
        k: {
            "status": "UNKNOWN",
            "value": "",
            "as_of": None,
            "searched_on": None,
            "source": "",
            "confidence": "",
            "updated_by": "",
            "note": "",
        }
        for k in ALL_KILL_SIGNALS
    }
    for k in NUMERIC_STREAKS:
        sig[k]["history"] = []
        sig[k]["streak"] = 0
    sig["KS-2"]["guides"] = {}
    return {
        "schema_version": 1,
        "last_weekly_run": None,
        "last_daily_run": None,
        "earnings_calendar": {},
        "kill_signals": sig,
        "iran_exit": {
            "status": "UNKNOWN",
            "brent": "",
            "ceasefire_state": "",
            "as_of": None,
            "searched_on": None,
            "source": "",
            "confidence": "",
            "updated_by": "",
        },
        "tqqq": {
            "zone": None,
            "drawdown_pct": "",
            "vix": "",
            "zone_since": None,
            "weeks_in_zone": 0,
            "as_of": None,
            "updated_by": "",
        },
    }


def load_signal_state() -> dict:
    """Load data/signal_state.json, or return a default skeleton."""
    if not SIGNAL_STATE_FILE.exists():
        return _default_signal_state()
    try:
        state = json.loads(SIGNAL_STATE_FILE.read_text())
        if not isinstance(state, dict) or "kill_signals" not in state:
            print("WARNING: signal_state.json has unexpected shape; "
                  "starting from defaults.", file=sys.stderr)
            return _default_signal_state()
        return state
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: could not read signal_state.json ({exc}); "
              "starting from defaults.", file=sys.stderr)
        return _default_signal_state()


def format_signal_state_block(state: dict, today: str) -> str:
    """Render signal state as a prompt-injectable text block.

    Includes staleness annotations like '(searched 06-15, 5 days ago)' so the
    model knows how old each reading is.
    """
    # Detect first run (all UNKNOWN)
    all_unknown = all(
        state.get("kill_signals", {}).get(k, {}).get("status") == "UNKNOWN"
        for k in ALL_KILL_SIGNALS
    )
    if all_unknown and state.get("iran_exit", {}).get("status") == "UNKNOWN":
        return ("No prior signal state on file. This is the first tracked run.\n"
                "Classify all kill signals and Iran exit from scratch based on "
                "your searches.")

    def staleness(searched_on: str | None) -> str:
        if not searched_on:
            return "(never searched)"
        try:
            delta = (datetime.strptime(today, "%Y-%m-%d")
                     - datetime.strptime(searched_on, "%Y-%m-%d")).days
        except ValueError:
            return f"(searched {searched_on})"
        if delta == 0:
            return f"(searched {searched_on}, today)"
        return f"(searched {searched_on}, {delta} day{'s' if delta != 1 else ''} ago)"

    lines = []
    lw = state.get("last_weekly_run") or "never"
    ld = state.get("last_daily_run") or "never"
    lines.append(f"Last weekly run: {lw}")
    lines.append(f"Last daily run:  {ld}")
    lines.append("")
    lines.append("Kill signals (carry forward any you do not search; "
                 "set source to 'carried forward'):")

    for ks_id in ALL_KILL_SIGNALS:
        ks = state.get("kill_signals", {}).get(ks_id, {})
        status = ks.get("status", "UNKNOWN")
        value = ks.get("value", "—")
        src = ks.get("source", "—")
        conf = ks.get("confidence", "—")
        note = ks.get("note", "")
        stale = staleness(ks.get("searched_on"))
        line = f"  {ks_id}: {status} | \"{value}\" | {stale} | [{src}][{conf}]"
        if note:
            line += f" | {note}"
        lines.append(line)
        spec = NUMERIC_STREAKS.get(ks_id)
        if spec:
            hist = ks.get("history") or []
            if hist:
                readings = ", ".join(
                    f"{h['period']}: {h['pct']:+.1f}%" for h in hist[-4:]
                )
                lines.append(
                    f"       {spec['label']} history: {readings} | "
                    f"script-computed streak: {ks.get('streak', 0)} of "
                    f"{spec['needed']} consecutive at ≤{spec['threshold']:.0f}% "
                    f"(trust this streak over any prose note)"
                )
            else:
                lines.append(
                    f"       {spec['label']} history: none yet — include "
                    f"\"{spec['value_key']}\" + \"{spec['period_key']}\" in your "
                    f"JSON block when you find a reading"
                )
        if ks_id == "KS-2":
            guides = ks.get("guides") or {}
            if guides:
                parts = ", ".join(
                    f"{n} {g['pct']:+.1f}% ({g['quarter']})"
                    for n, g in sorted(guides.items())
                )
                below = ", ".join(ks.get("below_10") or []) or "none"
                warn = ", ".join(ks.get("warn_10_13") or []) or "none"
                lines.append(f"       CapEx guides on file: {parts}")
                lines.append(
                    f"       script-computed ({ks.get('guide_quarter')}): "
                    f"below 10%: {below} | 10-13% warn band: {warn} | "
                    f"kill = 2+ below 10% same quarter (trust this count)"
                )
            else:
                lines.append(
                    "       CapEx guides: none tracked yet — emit \"guides\" in "
                    "your JSON block when a hyperscaler issues CapEx guidance"
                )

    iran = state.get("iran_exit", {})
    iran_status = iran.get("status", "UNKNOWN")
    iran_brent = iran.get("brent", "—")
    iran_cease = iran.get("ceasefire_state", "—")
    iran_src = iran.get("source", "—")
    iran_conf = iran.get("confidence", "—")
    iran_stale = staleness(iran.get("searched_on"))
    lines.append("")
    lines.append(f"Iran exit: {iran_status} | Brent {iran_brent} | "
                 f"ceasefire: {iran_cease} | {iran_stale} | "
                 f"[{iran_src}][{iran_conf}]")

    tqqq = state.get("tqqq", {})
    zone = tqqq.get("zone") or "unknown"
    dd = tqqq.get("drawdown_pct") or "—"
    vix = tqqq.get("vix") or "—"
    zs = tqqq.get("zone_since") or "—"
    wiw = tqqq.get("weeks_in_zone", 0)
    lines.append("")
    lines.append(f"TQQQ zone: {zone} | drawdown {dd}% | VIX {vix} | "
                 f"zone since {zs} | {wiw} weeks in zone")
    if zone == "near_ath":
        lines.append("  (Taxable TQQQ rotation requires 3-4 weeks in zone. "
                     f"Currently at {wiw} weeks.)")

    cal = state.get("earnings_calendar") or {}
    lines.append("")
    if cal:
        cal_s = " | ".join(f"{n} {d}" for n, d in sorted(cal.items()))
        lines.append("Earnings calendar (drives the daily's KS-2/AS-1 "
                     f"escalation): {cal_s}")
        lines.append("  (weekly: refresh stale/passed dates via "
                     "\"earnings_calendar\" in your JSON block)")
    else:
        lines.append("Earnings calendar: none on file — weekly should emit "
                     "\"earnings_calendar\" in its JSON block with the next "
                     "report dates for MSFT/GOOG/AMZN/META/NVDA.")

    return "\n".join(lines)


def compute_tqqq_zone(drawdown_pct: float) -> str:
    """Classify TQQQ zone from QQQ drawdown percentage."""
    if drawdown_pct < 10:
        return "near_ath"
    elif drawdown_pct < 20:
        return "pullback"
    return "deep_correction"


def update_tqqq_state(state: dict, snap: dict, today: str, tier: str) -> None:
    """Compute and update the tqqq block in-place from snapshot data.

    Resets zone_since when the zone changes; preserves it on same-zone re-runs
    so weeks_in_zone never inflates from re-runs.
    """
    dd_data = snap.get("qqq_drawdown", {})
    dd_pct = dd_data.get("drawdown_pct")
    if not isinstance(dd_pct, (int, float)):
        return  # can't compute zone without drawdown data

    new_zone = compute_tqqq_zone(dd_pct)
    old_zone = state.get("tqqq", {}).get("zone")
    old_zone_since = state.get("tqqq", {}).get("zone_since")

    if new_zone != old_zone or not old_zone_since:
        zone_since = today
    else:
        zone_since = old_zone_since

    try:
        weeks = (datetime.strptime(today, "%Y-%m-%d")
                 - datetime.strptime(zone_since, "%Y-%m-%d")).days // 7
    except (ValueError, TypeError):
        weeks = 0

    vix_level = snap.get("vix", {}).get("level")
    state["tqqq"] = {
        "zone": new_zone,
        "drawdown_pct": f"{dd_pct:.2f}",
        # VIX now comes from fetch_data (^VIX); fall back to the prior stored
        # value if the fetch failed.
        "vix": (f"{vix_level:.1f}" if isinstance(vix_level, (int, float))
                else state.get("tqqq", {}).get("vix", "")),
        "zone_since": zone_since,
        "weeks_in_zone": weeks,
        "as_of": today,
        "updated_by": tier,
    }


_SIGNAL_STATE_RE = re.compile(
    r"<!--\s*SIGNAL_STATE_JSON\s*\n(.*?)\nSIGNAL_STATE_JSON\s*-->",
    re.DOTALL,
)


def extract_model_signals(report_text: str) -> dict | None:
    """Extract the model's signal classifications from the hidden JSON block.

    Returns dict with keys 'kill_signals' and 'iran_exit', or None on failure.
    """
    m = _SIGNAL_STATE_RE.search(report_text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        print(f"WARNING: SIGNAL_STATE_JSON block found but invalid JSON: {exc}",
              file=sys.stderr)
        return None
    if not isinstance(data, dict):
        return None
    if "kill_signals" not in data or "iran_exit" not in data:
        print("WARNING: SIGNAL_STATE_JSON missing required keys "
              "(kill_signals / iran_exit).", file=sys.stderr)
        return None
    return data


def merge_model_signals(state: dict, model_data: dict, today: str,
                        tier: str, extra_searched=()) -> None:
    """Merge model-provided classifications into the state dict in-place.

    For each signal the model provides:
      - Overwrites status, value, source, confidence, note
      - Sets as_of = today, updated_by = tier
      - Sets searched_on = today ONLY if the tier is authorized to search it
    Signals omitted from model_data are left completely untouched.

    extra_searched: signals the daily was temporarily authorized to search this
    run (earnings-day escalation — KS-2 on a hyperscaler report, AS-1 on NVDA).
    """
    model_ks = model_data.get("kill_signals", {})
    for ks_id in ALL_KILL_SIGNALS:
        if ks_id not in model_ks:
            continue
        mk = model_ks[ks_id]
        existing = state["kill_signals"].get(ks_id, {})
        searched_on = existing.get("searched_on")
        # Daily is authorized to search KS-1 and KS-W; weekly searches all.
        if tier == "weekly" or ks_id in DAILY_SEARCHED_SIGNALS \
                or ks_id in extra_searched:
            searched_on = today
        new_entry = {
            "status": mk.get("status", existing.get("status", "UNKNOWN")),
            "value": mk.get("value", existing.get("value", "")),
            "as_of": today,
            "searched_on": searched_on,
            "source": mk.get("source", existing.get("source", "")),
            "confidence": mk.get("confidence", existing.get("confidence", "")),
            "updated_by": tier,
            "note": mk.get("note", existing.get("note", "")),
        }
        spec = NUMERIC_STREAKS.get(ks_id)
        if spec:
            new_entry["history"] = existing.get("history", [])
            _update_streak_history(new_entry, mk, spec)
        if ks_id == "KS-2":
            new_entry["guides"] = existing.get("guides", {})
            _update_capex_guides(new_entry, mk)
        state["kill_signals"][ks_id] = new_entry

    # Earnings calendar — either tier may refresh dates it learned this run.
    model_cal = model_data.get("earnings_calendar")
    if isinstance(model_cal, dict):
        cal = state.setdefault("earnings_calendar", {})
        for name, d in model_cal.items():
            n = str(name).upper()
            if n in EARNINGS_WATCH and isinstance(d, str) and _DATE_RE.match(d):
                cal[n] = d

    # Iran exit — both tiers search it.
    mi = model_data.get("iran_exit", {})
    if mi:
        state["iran_exit"] = {
            "status": mi.get("status", state["iran_exit"].get("status", "UNKNOWN")),
            "brent": mi.get("brent", state["iran_exit"].get("brent", "")),
            "ceasefire_state": mi.get("ceasefire_state",
                                      state["iran_exit"].get("ceasefire_state", "")),
            "as_of": today,
            "searched_on": today,
            "source": mi.get("source", state["iran_exit"].get("source", "")),
            "confidence": mi.get("confidence",
                                  state["iran_exit"].get("confidence", "")),
            "updated_by": tier,
        }


def save_signal_state(state: dict) -> None:
    """Atomically write signal state to data/signal_state.json.

    Uses write-to-temp-then-rename for crash safety. Warns on failure but
    never raises — the report is still valid even if state persistence fails.
    """
    try:
        SIGNAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=SIGNAL_STATE_FILE.parent, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, SIGNAL_STATE_FILE)
        except Exception:
            # Clean up temp file on failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        print(f"WARNING: could not save signal_state.json: {exc}",
              file=sys.stderr)


def strip_signal_block(report_text: str) -> str:
    """Remove the hidden SIGNAL_STATE_JSON block from the report.

    Called before saving to output/ and emailing — the reader never sees it.
    """
    cleaned = _SIGNAL_STATE_RE.sub("", report_text)
    # Clean up any resulting trailing blank lines.
    return cleaned.rstrip() + "\n" if cleaned.strip() else cleaned


def build_prompt(thesis: str, market_block: str, today: str, delta_block: str = "", signal_block: str = "") -> str:
    return f"""You are the ETF Research Agent described in the CLAUDE.md below. \
Produce today's pre-market research brief in markdown, following the exact \
REPORT STRUCTURE and REPORT RULES in CLAUDE.md.

Today's date: {today}

=== BEGIN CLAUDE.md (full thesis + portfolio context) ===
{thesis}
=== END CLAUDE.md ===

=== BEGIN MARKET DATA (from data/snapshot.json) ===
{market_block}
=== END MARKET DATA ===

=== BEGIN DAY-OVER-DAY DELTA (vs prior archived session) ===
{delta_block or "No prior snapshot on file — this is the first tracked run, so there is no day-over-day delta. Note this in the What Changed section."}
=== END DAY-OVER-DAY DELTA ===

=== BEGIN SIGNAL STATE (carry forward what you did not search) ===
{signal_block or "No signal state on file — first tracked run. Classify all kill signals and Iran exit from scratch based on your searches."}
=== END SIGNAL STATE ===

Output requirements:
- Markdown only, ready to render (the email renders markdown tables as real \
HTML tables, so prefer tables for any structured/tabular data). No code fences \
around the whole report.
- Output ONLY the report. No preamble, no lead-in sentence, no "here is your \
brief", no commentary about searching or exporting files. Your very first \
characters must be the report's "# " title line.
- Follow Sections 1–9 in order as defined in CLAUDE.md. Do NOT stop early — \
Sections 8 (Upcoming Events) and 9 (Radar) must both be present.
- "What Changed Since Last Report": immediately AFTER Section 1 (TL;DR) and \
before Section 2, add a highlighted block titled "## 🔄 What Changed Since Last \
Report". Lead with what is DIFFERENT vs the prior session, using the DELTA data \
above plus any thesis/news state changes you found via search (e.g. a kill \
signal moving CLEAR→APPROACHING, an Iran trigger getting closer, RSI flipping \
overbought, a candidate pulling back into buy range, a fresh catalyst). 3–6 \
bullets, each a genuine delta — not a restatement of today's levels. If the \
prior session's market bars match today's (markets closed), say so and focus on \
news/thesis changes only. If there is no prior snapshot, state that this is the \
first tracked run.
- Section 2 (TQQQ Signal Dashboard) must use the drawdown number above.
- Section 4 (Company Intelligence) must be reader-friendly and scannable:
  • Open with a compact "Exposure Summary" markdown table: \
Company | Today | Your Held Exposure | Gap / Candidate.
  • Then one short detail block per company: a `### COMPANY` subheader, a \
single tight paragraph, a bold "Your exposure:" line of `ETF (weight%)` chips \
separated by " · ", and a bold "Gap / Candidate:" line naming the best-fit \
candidate ETF from the watchlist pool when no held ETF covers it well.
- Potential Buys callout: immediately AFTER Section 6, add a highlighted block \
titled "## ⭐ Potential Buys — New Candidates". Pull from the candidate / \
watchlist ETFs above. Select and CYCLE 2–4 names each report based on that \
day's conditions (RSI oversold, pullback from 52w high, volume spike) and any \
binary event/catalyst. Render as a table: Candidate | Price | Day % | RSI | \
% off 52w High | Why now | Thesis layer. Then one line each on the highlighted \
names. If nothing is compelling today, say so in one line rather than forcing \
picks. These are candidates, NOT held — never present as owned, never \
recommend the underlying stock.
- Section 5 (Kill Signals) must list all 7 with status per CLAUDE.md — the 6 \
memory signals plus AS-1 (Layer 1 ASIC substitution: search NVIDIA data-center \
revenue trend and hyperscaler custom-silicon / TPU / Trainium / Maia \
substitution news to classify it).
- Section 6 must include the ETF Dashboard table populated from the market data.
- Action items in Section 7 must nominate ETFs only — never individual stocks.
- Section 9 (Radar) caps at 5 names; map each to an ETF, never recommend stocks.
- SOLD — do not list as holdings anywhere: FCG (stop loss), USO/XOP (Iran EXIT \
signal, 2026-07), SOXL (2026-07). The power/grid layer now has a STARTER GRID \
position only — flag the remaining underweight and surface the watchlist \
candidates (NLR/URNM/URA/PAVE) as the fill.
- Use only the market data provided for PRICES. If a price value is missing or \
stale, note it explicitly rather than inventing numbers.
- You HAVE web search and web fetch tools — USE THEM. Run the searches the \
CLAUDE.md DATA SOURCES section mandates every report: Iran conflict / Strait of \
Hormuz status; DRAM/HBM spot pricing (TrendForce/DRAMeXchange) for KS-1; \
hyperscaler CapEx news (MSFT/GOOG/AMZN/META) for KS-2; semiconductor sector \
news (NVDA/TSMC/SK Hynix/Samsung). Search the "when relevant" items (CXMT, \
helium, grid/power/nuclear) if the day's data warrants. Prefer recent, \
reputable sources; today's date is the anchor for "recent."
- SOURCE + CONFIDENCE TAGS. When a claim rests on something you found via \
search, tag it: [source1, source2][confidence — basis]. List the actual \
outlets (corroborate across 2+ independent ones where the claim is material), \
then a confidence level and its basis. E.g. \
"[Reuters, Bloomberg, TrendForce][high — multiple independent]" or \
"[VideoCardz][med — single source, formal spec pending]". \
Confidence rules (enforce, do not inflate):
    high = 2+ independent reputable sources agree
    med  = single source, OR sources tracing to one origin, OR a reputable \
source on a still-developing/unconfirmed story
    low  = rumor, social chatter, unconfirmed, or your own inference vs reporting
  A single-source claim CANNOT be high. A tentative/unsigned/pending item \
CANNOT be high (e.g. an unsigned MOU is med at best). State the basis so the \
reader knows what would change the rating. Do not fabricate sources — if search \
returns nothing material, say so and fall back to price/RSI/volume action \
(tag that "[no source — inferred from price action][low]").
- COUNTER-ARGUMENT on high-conviction calls. For every actionable/high- \
conviction claim — Section 7 action items, the Potential Buys picks, any thesis \
layer you call INTACT, and any kill signal you call CLEAR with conviction — \
include one specific, falsifiable counter-argument: the concrete mechanism by \
which the call could be wrong. Tie it to the relevant kill signal where one \
exists ("this breaks if KS-2 triggers — watch hyperscaler CapEx guides"). No \
generic hedging like "risks remain, monitor closely" — name the actual failure \
mode. If you genuinely cannot construct a credible counter, say so explicitly \
(that itself is signal).
- Kill signals and Iran exit triggers must reflect what you actually found in \
search this run, not generic priors.
- QUANTIFY PROXIMITY for every kill signal (Section 5) and every Iran exit \
trigger (Section 3). Don't just say CLEAR/HOLD — state the numeric distance to \
the trigger using the current value you found: "% of kill" (current ÷ \
threshold) and/or absolute gap. E.g. "helium $144.58 vs $300 = 48% of kill"; \
"Brent $91.12 vs $85 exit = $6.12 above trigger"; "SK Hynix OPM 72% vs 60% \
floor = 12 pts above". If a signal's current value isn't available from search, \
write "no fresh data" and give the last known reading rather than guessing.
- End with the disclaimer footer required by CLAUDE.md.
- SIGNAL STATE JSON BLOCK: After the disclaimer footer, on a new line, emit an \
invisible JSON block with your signal classifications. This block is machine- \
parsed by the script and stripped before the report is saved/emailed — the \
reader never sees it. Emit it EXACTLY in this format (including the HTML \
comment delimiters):

<!-- SIGNAL_STATE_JSON
{{"kill_signals": {{"KS-1": {{"status": "CLEAR", "value": "...", "mom_pct": -2.5, "month": "2026-06", "source": "...", "confidence": "...", "note": ""}}, "KS-2": {{"status": "...", "value": "...", "guides": {{"MSFT": {{"pct": 24.0, "quarter": "2026-Q2"}}}}, "source": "...", "confidence": "...", "note": ""}}, "KS-3": {{"status": "...", "value": "...", "source": "...", "confidence": "...", "note": ""}}, "KS-4": {{"status": "...", "value": "...", "qoq_pct": -1.0, "quarter": "2026-Q2", "source": "...", "confidence": "...", "note": ""}}, "KS-5": {{"status": "...", "value": "...", "source": "...", "confidence": "...", "note": ""}}, "KS-W": {{"status": "...", "value": "...", "source": "...", "confidence": "...", "note": ""}}, "AS-1": {{"status": "...", "value": "...", "qoq_pct": 5.0, "quarter": "2026-Q2", "source": "...", "confidence": "...", "note": ""}}}}, "iran_exit": {{"status": "HOLD", "brent": "...", "ceasefire_state": "...", "source": "...", "confidence": "..."}}, "earnings_calendar": {{"MSFT": "2026-07-29", "GOOG": "2026-07-28", "AMZN": "2026-07-30", "META": "2026-07-29", "NVDA": "2026-08-26"}}}}
SIGNAL_STATE_JSON -->

Rules for the JSON block:
  - status: exactly one of CLEAR, APPROACHING, TRIGGERED (kill signals) or \
HOLD, APPROACHING, EXIT (Iran exit).
  - value: the current reading you found or carried forward (string).
  - KS-1, KS-4 and AS-1 are consecutive-period conditions, tracked numerically \
by the script: for KS-1 also emit "mom_pct" (latest month-over-month DRAM spot \
% change, as a NUMBER) and "month" ("YYYY-MM"); for KS-4 emit "qoq_pct" \
(NUMBER) and "quarter" ("YYYY-Qn"); for AS-1 emit "qoq_pct" = NVIDIA \
data-center revenue quarter-over-quarter % change and "quarter". Report only \
the LATEST reading — the script keeps the period history and computes the \
streak toward the kill condition itself. Omit these fields when you found no \
numeric reading this run.
  - KS-2: when any hyperscaler issued CapEx guidance since the last reading, \
emit "guides" with one entry per name (MSFT/GOOG/AMZN/META): "pct" = guided \
CapEx growth % (NUMBER) and "quarter" = the quarter the guide covers. The \
script keeps the per-name table and counts the kill condition (2+ below 10% \
same quarter) itself. Omit names with no new guidance.
  - earnings_calendar: emit the NEXT confirmed earnings report date \
("YYYY-MM-DD") for MSFT, GOOG, AMZN, META, NVDA — refresh any date that has \
passed. This drives the daily tier's KS-2/AS-1 escalation. Omit names whose \
next date you could not confirm.
  - source: the outlet(s) you found this from. For signals you did NOT search \
this run, set to "carried forward".
  - confidence: high, med, or low.
  - note: brief context, or empty string.
  - Include ALL 7 kill signals (KS-1..KS-W + AS-1) and iran_exit every time.
  - The JSON must be valid — no trailing commas, no comments inside it.
  - The values must be consistent with what you wrote in the report body.
"""


def call_claude(prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        die("anthropic SDK not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY is not set.\n\n"
            "Set it for this shell session with:\n"
            "    export ANTHROPIC_API_KEY=sk-ant-...\n\n"
            "Or add the line above to ~/.zshrc to make it permanent, then run:\n"
            "    source ~/.zshrc\n\n"
            "Get a key at https://console.anthropic.com/settings/keys",
            file=sys.stderr,
        )
        sys.exit(2)

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": prompt}]

    # Stream the call (avoids HTTP timeouts on long, search-heavy runs) and use
    # adaptive thinking for the synthesis. Web search/fetch run server-side; if
    # the server tool loop hits its iteration cap the response comes back with
    # stop_reason == "pause_turn" and we re-send to resume.
    resp = None
    container_id = None
    try:
        for _ in range(MAX_CONTINUATIONS):
            # The web tools' dynamic filtering runs server-side code execution,
            # which spins up a container. On pause_turn resume we MUST pass that
            # container id back, or the API rejects the continuation with
            # "container_id is required when there are pending tool uses".
            kwargs = {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "thinking": {"type": "adaptive"},
                "tools": WEB_TOOLS,
                "messages": messages,
            }
            if container_id is not None:
                kwargs["container"] = container_id

            with client.messages.stream(**kwargs) as stream:
                resp = stream.get_final_message()

            # Carry the container forward for any subsequent continuation.
            container = getattr(resp, "container", None)
            if container is not None and getattr(container, "id", None):
                container_id = container.id

            if resp.stop_reason != "pause_turn":
                break
            # Resume: append the paused assistant turn and call again. The server
            # detects the trailing server_tool_use block and continues.
            messages.append({"role": "assistant", "content": resp.content})
        else:
            print(
                "WARNING: hit MAX_CONTINUATIONS while resuming web-search turns; "
                "report may be incomplete.",
                file=sys.stderr,
            )
    except anthropic.APIStatusError as exc:
        die(f"Anthropic API error ({exc.status_code}): {exc.message}")
    except anthropic.APIConnectionError as exc:
        die(f"Could not reach the Anthropic API: {exc}")
    except Exception as exc:  # noqa: BLE001
        die(f"Unexpected API failure: {type(exc).__name__}: {exc}")

    if resp is None:
        die("No response returned from the Anthropic API.")

    if resp.stop_reason == "max_tokens":
        print(
            "WARNING: response hit max_tokens — report may be truncated. "
            f"Consider raising MAX_TOKENS (currently {MAX_TOKENS}).",
            file=sys.stderr,
        )

    parts = [block.text for block in resp.content if getattr(block, "type", None) == "text"]
    return _strip_preamble("\n".join(parts).strip())


def _strip_preamble(text: str) -> str:
    """Drop any conversational lead-in the model emits before the report.

    With web search + thinking the model sometimes narrates ("Now I have the
    data... here is your brief...") before the markdown. The report proper always
    begins at its first markdown heading, so cut everything before that.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            return "\n".join(lines[i:]).strip()
    return text.strip()  # no heading found — return as-is rather than blanking it


def main() -> int:
    snap = load_snapshot()
    thesis = load_thesis()
    market_block = format_market_block(snap)

    prior = load_prior_snapshot(snap)
    delta_block = format_delta_block(snap, prior)
    if prior:
        print(
            f"Delta vs prior session {prior.get('generated_at_utc', '?')[:10]}.",
            file=sys.stderr,
        )
    else:
        print("No prior snapshot found — first tracked run, no delta.", file=sys.stderr)

    # Signal state: read prior run's classifications.
    signal_state = load_signal_state()
    today = date.today().isoformat()
    signal_block = format_signal_state_block(signal_state, today)

    prompt = build_prompt(thesis, market_block, today, delta_block, signal_block)

    print(f"Generating brief for {today} via {MODEL}…", file=sys.stderr)
    report = call_claude(prompt)

    # Empty-output guard. If the model produced no usable report (e.g. it spent
    # the whole token budget on thinking/search, or only emitted preamble with
    # no "# " heading), do NOT save or email junk. die() exits non-zero so
    # run_weekly.sh aborts before send_email.py runs.
    if not report or not report.strip():
        die(
            "Weekly brief came back EMPTY — nothing saved, nothing sent. The "
            "model likely exhausted MAX_TOKENS on thinking/search before "
            f"writing any report text (MAX_TOKENS={MAX_TOKENS}). Retry."
        )

    # Signal state: write back (TQQQ zone + model classifications).
    update_tqqq_state(signal_state, snap, today, "weekly")
    model_data = extract_model_signals(report)
    if model_data:
        merge_model_signals(signal_state, model_data, today, "weekly")
    else:
        print("WARNING: could not extract signal state from model output; "
              "state file unchanged for kill signals / Iran exit.",
              file=sys.stderr)
    signal_state["last_weekly_run"] = today
    save_signal_state(signal_state)

    # Strip the hidden JSON block before saving the reader-facing report.
    report = strip_signal_block(report)

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        die(f"Could not create output dir {OUTPUT_DIR}: {exc}")

    out_path = OUTPUT_DIR / f"{today}-brief.md"
    out_path.write_text(report)

    print()
    print(report)
    print()
    print(f"Saved to {out_path.relative_to(PROJECT_DIR)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
