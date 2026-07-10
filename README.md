# Market Report Agent

An automated pre-market research system for an ETF portfolio built around an
AI-infrastructure investment thesis. Each morning it pulls market data, has
Claude run a set of targeted web searches, checks the thesis against
pre-defined warning conditions ("kill signals"), and emails the result. There
are two report tiers: a full weekly brief and a short daily check.

## How it works

```
fetch_data.py            generate_brief.py / daily_pulse.py         send_email.py
┌────────────────┐       ┌──────────────────────────────────┐      ┌───────────┐
│ yfinance:      │       │ Claude + web search              │      │ Gmail     │
│ price, RSI,    │──────▶│  · thesis spec (CLAUDE.md)       │─────▶│ HTML      │
│ volume, VIX,   │       │  · market snapshot + deltas      │      │ email     │
│ 52w highs      │       │  · saved signal state            │      └───────────┘
└───────┬────────┘       └───────────────┬──────────────────┘
        │                                │ signal-state write-back
        ▼                                ▼
  data/history/*.json          data/signal_state.json
  (day-over-day deltas)        (signal readings between runs)
```

1. `fetch_data.py` pulls price, RSI, volume, VIX, and 52-week highs from
   yfinance into `data/snapshot.json`, and archives a daily copy so the next
   run can compute day-over-day changes.
2. `generate_brief.py` (weekly) or `daily_pulse.py` (daily) sends the
   snapshot, the thesis spec in `CLAUDE.md`, and the saved signal state to
   Claude, which runs its web searches and writes the report. Updated signal
   readings are written back to `data/signal_state.json`, so classifications
   carry over between runs instead of being re-derived each time.
3. `send_email.py` delivers the report via Gmail.

The two tiers:

| | Weekly brief | Daily pulse |
|---|---|---|
| Model | Claude Opus | Claude Sonnet |
| Scope | Full 9-section report: macro context, company news mapped to ETF exposure, every signal re-checked, buy candidates, watchlist | Short check: how holdings moved since the prior session, plus the fast-moving signals |
| Web searches | Every signal searched fresh | At most 2, plus one extra the morning after a tracked earnings report |
| On a normal day | Full report | A few lines saying nothing changed |

## The thesis

The portfolio is built on one idea: AI software is improving faster than the
physical infrastructure it runs on, so the durable value is in the
infrastructure layers rather than the applications. The thesis has four
layers, each mapped to ETFs:

1. **Compute / silicon** — chip design and manufacturing.
2. **Memory bandwidth** — the DRAM/HBM makers; the highest-conviction layer.
3. **Power / grid** — electricity and grid capacity for datacenters; mostly
   still an acknowledged gap in the portfolio.
4. **Leveraged QQQ** — a tactical layer that scales leverage up during
   pullbacks and back down near highs.

The full thesis — the reasoning behind each layer, monitoring lists, and the
report formats — lives in [CLAUDE.md](CLAUDE.md), which is also the spec the
agent reads at generation time.

## Kill signals and how to read them

A kill signal is a numeric condition, written down in advance, under which
part of the thesis should be considered wrong. For example: "DRAM spot price
falls 10% per month for 3 consecutive months." Writing the exit conditions
down ahead of time keeps the system from rationalizing bad news later.

Each signal has two thresholds:

- the **kill** condition — the full trigger, and
- a **tripwire** — a softer early-warning level some distance before it.

Every report classifies every signal as one of three statuses:

- `CLEAR` — not near the tripwire
- `APPROACHING` — past the tripwire but not the trigger; this is what makes
  the daily pulse start alerting
- `TRIGGERED` — the kill condition is fully met

Alongside the status, each signal reports its current reading and its
distance from the trigger (e.g. "helium $145 vs $300 trigger — 48% of the
way"), so a comfortable CLEAR reads differently from a close one. The
tripwire numbers are plain text in CLAUDE.md and can be tuned: tighter for
earlier warnings, looser for fewer alerts.

## Other conventions

- The scripts compute everything that can be computed deterministically
  (consecutive-month streaks, drawdown zones, guidance counts, earnings-day
  escalations); the model only classifies what needs judgment.
- Every claim from web research carries a source-and-confidence tag, and
  single-source claims are never marked high confidence. Stale readings are
  labeled as stale rather than re-asserted.
- Actionable recommendations include a specific counter-argument — the
  concrete way the call could be wrong.
- Failures are surfaced rather than papered over: all-null data snapshots are
  not archived (they would corrupt the next day's deltas), empty model output
  stops the pipeline before the email step, and a failed scheduled run sends
  an alert email.

## Repository map

```
CLAUDE.md              agent spec: thesis, signals, tripwires, report formats
fetch_data.py          market data + VIX via yfinance → data/snapshot.json
generate_brief.py      weekly brief + the shared signal-state machinery
daily_pulse.py         daily pulse (imports the shared machinery)
send_email.py          delivers the latest report via Gmail (HTML + plaintext)
send_alert.py          emails the owner when a scheduled run fails
run_daily.sh / run_weekly.sh / run_scheduled.sh    pipeline runners (launchd-ready)
.env.example           required environment variables, documented
portfolio.example.md   template for the (gitignored) positions file
```

Personal data stays out of the repo: positions live in a gitignored
`portfolio.md` that is spliced into the prompt at generation time, and
credentials live in a gitignored `.env`.

## Setup

```bash
pip install anthropic yfinance pandas markdown

cp .env.example .env                      # add your API key + Gmail app password
cp portfolio.example.md portfolio.md      # fill in your positions

python fetch_data.py        # pull market data
python generate_brief.py    # generate the weekly brief  → output/
python daily_pulse.py       # or the daily pulse         → output/
python send_email.py        # email the latest report
```

For unattended runs, point `launchd` (or cron) at `run_scheduled.sh`, which
loads `.env` and hands off to the tier runner — weekly on Mondays, daily the
rest of the trading week.

## Disclaimer

This is a personal research tool. Its output is AI-generated, for research
purposes only, and is not financial advice.
