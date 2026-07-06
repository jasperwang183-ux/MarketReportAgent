# Market Report Agent

An automated, two-tier pre-market research system for a thesis-driven ETF
portfolio. Every morning it pulls market data, runs targeted web research
through Claude, checks a battery of quantified "kill signals" against the
investment thesis, and delivers a report by email — a deep weekly brief, and a
lean daily pulse that only shouts when something actually crosses a tripwire.

Built as a real system managing a real portfolio, not a demo: it has survived
data-provider outages, empty-output incidents, and model migrations, and the
design carries those scars deliberately.

## How it works

```
fetch_data.py            generate_brief.py / daily_pulse.py         send_email.py
┌────────────────┐       ┌──────────────────────────────────┐      ┌───────────┐
│ yfinance:      │       │ Claude + server-side web search  │      │ Gmail     │
│ price, RSI,    │──────▶│  · thesis spec (CLAUDE.md)       │─────▶│ HTML      │
│ volume, VIX,   │       │  · market snapshot + deltas      │      │ email     │
│ 52w highs      │       │  · persistent signal state       │      └───────────┘
└───────┬────────┘       └───────────────┬──────────────────┘
        │                                │ hidden JSON write-back
        ▼                                ▼
  data/history/*.json          data/signal_state.json
  (day-over-day deltas)        (kill-signal state machine)
```

**Two tiers, priced to their jobs:**

| | Weekly brief | Daily pulse |
|---|---|---|
| Model | Claude Opus | Claude Sonnet |
| Scope | Full 9-section deep report: macro, company intelligence mapped to ETF exposure, all signals re-searched, buy candidates, radar | Tripwire check: holdings quick-read + fast-moving signals only |
| Search budget | Full sweep, every signal | ≤2 searches, plus one authorized escalation the morning after a tracked earnings report |
| Voice | Authoritative reference | Exception-based — "🟢 ALL QUIET" on a normal day, shouts only on a tripwire |

## The signal framework

The thesis (in [CLAUDE.md](CLAUDE.md)) is only allowed to survive on evidence.
Each layer of the thesis carries **kill signals** — pre-committed, numeric
conditions under which the position is wrong — plus softer **tripwires** that
define when a signal moves from CLEAR to APPROACHING and the daily starts
alerting.

Design decisions worth stealing:

- **Quantified proximity, never vibes.** A signal is never just "CLEAR" — it's
  "48% of kill" or "12 pts above the floor". The distance is the information.
- **Deterministic where possible, model where necessary.** The scripts compute
  everything computable (consecutive-month streaks, rotation zones,
  guidance-count kill conditions, calendar escalations); the model only
  classifies what genuinely needs judgment. A carried-forward "month 2 of 3"
  is a fact in the state file, not a memory the model might drift on.
- **Honest epistemics, enforced.** Every researched claim carries
  `[sources][confidence — basis]` tags with anti-inflation rules (single-source
  is never "high"). The state file tracks `as_of` and `searched_on` separately,
  so a stale reading is labeled stale instead of silently re-asserted. Every
  high-conviction call must include a falsifiable counter-argument.
- **Earnings-calendar escalation.** The daily's search budget is capped, but
  the weekly maintains a calendar of the earnings dates that move the
  demand-side signals — and the morning after one, the daily is granted one
  extra authorized search for exactly that reading.
- **Fail loudly.** All-null data snapshots are never archived (they'd poison
  the next day's delta baseline), empty model output aborts the pipeline before
  the email step, and any stage failure triggers an alert email to the owner.

## Repository map

```
CLAUDE.md              the agent spec: thesis, signals, tripwires, report formats
fetch_data.py          market data + VIX via yfinance → data/snapshot.json
generate_brief.py      weekly deep brief + the shared signal-state machinery
daily_pulse.py         daily tripwire pulse (imports the shared machinery)
send_email.py          delivers the latest report via Gmail (HTML + plaintext)
send_alert.py          emails the owner when a scheduled run fails
run_daily.sh / run_weekly.sh / run_scheduled.sh    pipeline runners (launchd-ready)
.env.example           required environment variables, documented
portfolio.example.md   template for the (gitignored) positions file
```

Personal data never enters the repo: positions live in a gitignored
`portfolio.md` spliced into the prompt at generation time, and credentials
live in a gitignored `.env`.

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

## Roadmap

- **Cockpit** — a read-only web dashboard over the same state files
  (signal trajectories, headline log, report archive), served privately via
  Tailscale. The email stays the push channel; the cockpit becomes the pull
  channel.

## Disclaimer

This is a personal research tool. Its output is AI-generated, for research
purposes only, and is not financial advice.
