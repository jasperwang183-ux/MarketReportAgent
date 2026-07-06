"""
fetch_data.py — Pull market data for the ETF Research Agent.

For each ticker, fetches:
  - current price
  - daily % change
  - RSI(14)
  - 20-day average volume
  - current volume
  - 52-week high

Pulls QQQ explicitly so the TQQQ drawdown signal can be computed.
Writes a timestamped JSON snapshot to data/snapshot.json and prints
a summary table to the terminal.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


# Currently held ETFs. These drive the portfolio dashboard, the TQQQ drawdown
# signal, and the run.sh abort logic.
# 2026-07-06 holdings update: USO/XOP exited (Iran EXIT signal), SOXL exited
# (IRA leverage now TQQQ/QLD), GRID added (Layer 3 starter), QLD added (was
# held but previously missing from this list).
TICKERS = [
    "DRAM", "SMH", "TQQQ", "QLD", "VOO", "SPY",
    "QQQ", "CRAK", "EWY", "GRID",
]

# Candidate / watchlist universe — unowned but thesis-relevant ETFs. We fetch
# the same metrics for these so the brief can dynamically surface "potential
# buys" each report (Section 4 mapping + the Potential Buys callout), cycling
# which names it highlights based on that day's conditions and catalysts.
# These are NOT holdings: excluded from the drawdown signal and from the
# pipeline-abort check. Edit this list to reshape the candidate pool.
#   NLR  — nuclear energy (Layer 3 power gap)
#   URNM — uranium miners (Layer 3 power gap)
#   URA  — uranium / nuclear fuel (Layer 3 power gap)
#   PAVE — US infrastructure buildout (grid + datacenter adjacency)
#   NBIS — Nebius (neo-cloud / GPU capacity). NOTE: a STOCK, not an ETF — the
#          first name added under the stock-first direction. Pure-play neo-cloud
#          with no clean ETF wrapper; watched for the GPU-capacity layer.
WATCHLIST = ["NLR", "URNM", "URA", "PAVE", "NBIS"]

# A snapshot older than this many hours is flagged as stale.
STALE_AFTER_HOURS = 36

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_FILE = DATA_DIR / "snapshot.json"
# Dated archives so generate_brief.py can diff today vs the prior session for
# the "What Changed Since Last Report" delta section.
HISTORY_DIR = DATA_DIR / "history"



def compute_rsi(closes: pd.Series, period: int = 14) -> float | None:
    """Wilder's RSI. Returns None if not enough data."""
    if closes is None or len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    last_avg_gain = avg_gain.iloc[-1]
    last_avg_loss = avg_loss.iloc[-1]
    if last_avg_loss == 0:
        return 100.0
    rs = last_avg_gain / last_avg_loss
    rsi = 100 - (100 / (1 + rs))
    if pd.isna(rsi):
        return None
    return float(round(rsi, 2))


def fetch_ticker(ticker: str) -> dict:
    """Fetch one ticker. Always returns a dict; populates `error` on failure."""
    record: dict = {
        "ticker": ticker,
        "price": None,
        "day_change_pct": None,
        "rsi_14": None,
        "volume": None,
        "avg_volume_20d": None,
        "high_52w": None,
        "last_bar_date": None,
        "stale": False,
        "error": None,
    }
    try:
        tk = yf.Ticker(ticker)
        # 1y of daily bars covers 52-week high, RSI, and 20-day volume.
        hist = tk.history(period="1y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            record["error"] = "no history returned"
            return record

        closes = hist["Close"].dropna()
        volumes = hist["Volume"].dropna()
        if closes.empty:
            record["error"] = "no close prices"
            return record

        last_close = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
        record["price"] = round(last_close, 4)
        if prev_close and prev_close != 0:
            record["day_change_pct"] = round((last_close / prev_close - 1) * 100, 3)

        record["rsi_14"] = compute_rsi(closes, period=14)

        if not volumes.empty:
            record["volume"] = int(volumes.iloc[-1])
            tail = volumes.tail(20)
            if len(tail) > 0:
                record["avg_volume_20d"] = int(round(tail.mean()))

        # 52-week high from the trailing ~1y of bars.
        record["high_52w"] = round(float(hist["High"].max()), 4)

        last_idx = hist.index[-1]
        record["last_bar_date"] = last_idx.strftime("%Y-%m-%d")

        # Staleness: compare last bar to "now" in UTC.
        last_dt = last_idx.to_pydatetime()
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
        # Anything older than STALE_AFTER_HOURS over a weekend gets flagged.
        # Allow extra slack on Mondays for Friday close.
        weekday = datetime.now(timezone.utc).weekday()  # 0=Mon
        threshold = STALE_AFTER_HOURS + (48 if weekday == 0 else 0)
        record["stale"] = age_hours > threshold

    except Exception as exc:  # noqa: BLE001 — surface any yfinance failure
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def fetch_vix() -> dict:
    """VIX level + direction — the TQQQ rotation strategy's secondary signal.

    Not a holding, so it lives outside TICKERS/WATCHLIST. Direction compares the
    latest close to the prior 5-day average with a ±3% dead band, matching the
    rising / falling / flat read the report block expects.
    """
    rec = {"level": None, "day_change": None, "avg_5d": None,
           "direction": None, "error": None}
    try:
        hist = yf.Ticker("^VIX").history(period="1mo", interval="1d",
                                         auto_adjust=False)
        closes = hist["Close"].dropna() if hist is not None and not hist.empty else None
        if closes is None or closes.empty:
            rec["error"] = "no history returned"
            return rec
        level = float(closes.iloc[-1])
        rec["level"] = round(level, 2)
        if len(closes) >= 2:
            rec["day_change"] = round(level - float(closes.iloc[-2]), 2)
        if len(closes) >= 6:
            avg5 = float(closes.iloc[-6:-1].mean())
            rec["avg_5d"] = round(avg5, 2)
            if level > avg5 * 1.03:
                rec["direction"] = "rising"
            elif level < avg5 * 0.97:
                rec["direction"] = "falling"
            else:
                rec["direction"] = "flat"
    except Exception as exc:  # noqa: BLE001 — surface any yfinance failure
        rec["error"] = f"{type(exc).__name__}: {exc}"
    return rec


def build_snapshot() -> dict:
    rows = [fetch_ticker(t) for t in TICKERS]
    by_ticker = {r["ticker"]: r for r in rows}

    # Candidate / watchlist ETFs — fetched the same way, stored separately so
    # held-portfolio logic never treats them as holdings.
    watch_rows = [fetch_ticker(t) for t in WATCHLIST]
    by_watch = {r["ticker"]: r for r in watch_rows}

    # TQQQ drawdown signal: QQQ price vs QQQ 52-week high.
    qqq = by_ticker.get("QQQ", {})
    qqq_price = qqq.get("price")
    qqq_52w = qqq.get("high_52w")
    drawdown_pct = None
    if qqq_price and qqq_52w and qqq_52w > 0:
        drawdown_pct = round((qqq_52w - qqq_price) / qqq_52w * 100, 3)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": by_ticker,
        "watchlist": by_watch,
        "qqq_drawdown": {
            "qqq_price": qqq_price,
            "qqq_52w_high": qqq_52w,
            "drawdown_pct": drawdown_pct,
        },
        "vix": fetch_vix(),
        # Held-only — drives run.sh abort logic; watchlist issues are advisory.
        "errors": [r["ticker"] for r in rows if r["error"]],
        "stale": [r["ticker"] for r in rows if r["stale"]],
        "watchlist_errors": [r["ticker"] for r in watch_rows if r["error"]],
        "watchlist_stale": [r["ticker"] for r in watch_rows if r["stale"]],
    }


def print_summary(snapshot: dict) -> None:
    headers = [
        "Ticker", "Price", "Day %", "RSI(14)",
        "Vol", "20d Avg Vol", "52w High", "Last Bar", "Status",
    ]
    widths = [7, 10, 8, 8, 14, 14, 10, 11, 18]

    def fmt_row(vals):
        return "  ".join(str(v).rjust(w) for v, w in zip(vals, widths))

    def fmt_num(x, decimals=2):
        if x is None:
            return "—"
        return f"{x:,.{decimals}f}"

    def fmt_int(x):
        return "—" if x is None else f"{int(x):,}"

    def print_table(title, ticker_list, store_key):
        print(title)
        print(fmt_row(headers))
        print("  ".join("-" * w for w in widths))
        for ticker in ticker_list:
            rec = snapshot.get(store_key, {}).get(ticker, {})
            status_bits = []
            if rec.get("error"):
                status_bits.append(f"ERR: {rec['error'][:14]}")
            if rec.get("stale"):
                status_bits.append("STALE")
            status = ", ".join(status_bits) if status_bits else "ok"
            print(fmt_row([
                ticker,
                fmt_num(rec.get("price"), 2),
                fmt_num(rec.get("day_change_pct"), 2),
                fmt_num(rec.get("rsi_14"), 1),
                fmt_int(rec.get("volume")),
                fmt_int(rec.get("avg_volume_20d")),
                fmt_num(rec.get("high_52w"), 2),
                rec.get("last_bar_date") or "—",
                status,
            ]))

    print()
    print(f"Snapshot generated at {snapshot['generated_at_utc']}")
    print()
    print_table("HELD ETFs", TICKERS, "tickers")
    print()
    print_table("CANDIDATE / WATCHLIST ETFs (not held)", WATCHLIST, "watchlist")

    dd = snapshot["qqq_drawdown"]
    print()
    print("TQQQ Drawdown Signal (QQQ vs 52-week high)")
    print(f"  QQQ price:    {fmt_num(dd.get('qqq_price'), 2)}")
    print(f"  QQQ 52w high: {fmt_num(dd.get('qqq_52w_high'), 2)}")
    print(f"  Drawdown:     {fmt_num(dd.get('drawdown_pct'), 2)}%")

    vix = snapshot.get("vix", {})
    if vix.get("level") is not None:
        print(f"  VIX:          {fmt_num(vix['level'], 2)} "
              f"(Δ {fmt_num(vix.get('day_change'), 2)} vs prior close, "
              f"5d avg {fmt_num(vix.get('avg_5d'), 2)}, "
              f"{vix.get('direction') or 'direction unknown'})")
    else:
        print(f"  VIX:          unavailable ({vix.get('error') or 'no data'})")

    if snapshot["errors"]:
        print()
        print(f"Errors on: {', '.join(snapshot['errors'])}")
    if snapshot["stale"]:
        print(f"Stale data: {', '.join(snapshot['stale'])}")
    if snapshot.get("watchlist_errors"):
        print(f"Watchlist errors on: {', '.join(snapshot['watchlist_errors'])}")
    if snapshot.get("watchlist_stale"):
        print(f"Watchlist stale: {', '.join(snapshot['watchlist_stale'])}")
    print()


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot()
    payload = json.dumps(snapshot, indent=2)
    OUTPUT_FILE.write_text(payload)
    print_summary(snapshot)
    print(f"Wrote {OUTPUT_FILE.relative_to(PROJECT_DIR)}")

    # Archive a dated copy for day-over-day deltas. Keyed by the snapshot's UTC
    # date; a re-run on the same day overwrites it (idempotent). An all-failed
    # fetch is NOT archived — a null-price file would poison the next session's
    # delta baseline (the 2026-06-08 / 06-15 incidents).
    if len(snapshot["errors"]) >= len(TICKERS):
        print("WARNING: every held ticker errored — snapshot NOT archived "
              "(would poison the delta history).")
    else:
        try:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            archive_date = snapshot["generated_at_utc"][:10]  # YYYY-MM-DD
            archive_path = HISTORY_DIR / f"{archive_date}.json"
            archive_path.write_text(payload)
            print(f"Archived {archive_path.relative_to(PROJECT_DIR)}")
        except OSError as exc:
            # Non-fatal: the brief still generates, just without a fresh delta.
            print(f"WARNING: could not archive snapshot: {exc}")

    # Non-zero exit if every ticker errored so run.sh can stop early.
    return 0 if len(snapshot["errors"]) < len(TICKERS) else 1


if __name__ == "__main__":
    sys.exit(main())
