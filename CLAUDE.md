# CLAUDE.md — ETF Research Agent
# Last updated: June 2026
# Read this file at the start of every session.

---

## WHAT THIS PROJECT DOES

Two-tier pre-market research system for an ETF-only portfolio built on the AI
infrastructure thesis. Covers macro context, company intelligence mapped to ETF
exposure, memory thesis kill-signal monitoring, and TQQQ rotation signals.
Delivers via Gmail.

  **WEEKLY brief** (`generate_brief.py`, Opus) — full 9-section deep report:
  TL;DR, What Changed, TQQQ dashboard, macro, company intel + ETF mapping,
  memory kill-signal sweep, thesis-layer status + ETF dashboard, Potential Buys,
  action items, events, Radar. Runs the full search sweep across all signals.

  **DAILY pulse** (`daily_pulse.py`, Sonnet) — lean tripwire check: holdings
  quick read + kill-signal / Iran-exit check. Shouts only when a tripwire trips
  or a holding moves materially. On a quiet day it's a short heartbeat.

Both tiers read the same market snapshot (`data/snapshot.json` from
`fetch_data.py`) and the same thesis spec (this file). The daily imports the
weekly's shared data helpers so the two never drift on data shape.

---

## APPROACH TO INDIVIDUAL COMPANIES

This report covers individual company news and analysis freely — it informs
which ETFs to size up, rotate into, or trim.

Report format for every company mention:
→ One paragraph max on what happened or why it matters today
→ Immediately followed by ETF exposure mapping:
   "Your exposure: SMH (20.3%) | QQQ (8%) | VOO (3%)"
→ If none of your held ETFs cover it well, flag as an exposure gap
   with the best-fit ETF candidate noted

All ACTION ITEMS and RECOMMENDATIONS nominate ETFs only, never individual
stocks. Company analysis is the context; the ETF is the trade.

### Company-to-ETF Mapping Reference
Agent uses these approximate weights and web searches for updates when a
company is the primary focus of that day's report.

  NVIDIA:     SMH ~20% | QQQ ~8% | TQQQ ~8% (3x levered) | VOO/SPY ~3-4%
  TSMC:       SMH ~15% | QQQ indirect
  SK Hynix:   DRAM ~25% | EWY ~8%
  Samsung:    DRAM ~24% | EWY ~20%
  Micron:     DRAM ~24% | SMH ~3%
  Broadcom:   SMH ~8%  | QQQ ~4%
  AMD:        SMH ~5%  | QQQ ~2%
  Google:     QQQ ~9%  | TQQQ ~9% (3x) | VOO/SPY ~4%
  Amazon:     QQQ ~8%  | TQQQ ~8% (3x) | VOO/SPY ~3%
  Microsoft:  QQQ ~9%  | TQQQ ~9% (3x) | VOO/SPY ~7%
  Meta:       QQQ ~5%  | VOO/SPY ~2%
  Palantir:   QQQ indirect/small
  Tesla:      QQQ ~3%  | VOO/SPY ~1%

  Note: Weights drift over time. Web search for current weights when a
  specific company is the primary story that day.

---

## PORTFOLIO SNAPSHOT

Positions live in `portfolio.md` (gitignored — personal financial data; copy
`portfolio.example.md` to create it). At generation time, load_thesis() splices
its full contents in below. When working in this repo interactively, read
`portfolio.md` for current holdings.

<!-- PORTFOLIO_MD -->

---

## MASTER INVESTMENT THESIS: AI INFRASTRUCTURE STACK

Core belief: AI is improving exponentially on the software side. The bottleneck
will increasingly shift from software to physical infrastructure. Own the
infrastructure layers — compute, memory bandwidth, and power — not the apps.

### Layer 1 — Compute / Silicon
Thesis: AI accelerator demand outstrips supply through 2027+. TSMC manufacturing
and NVIDIA/AMD/Broadcom design are the chokepoints. TPU/custom silicon (Google,
Amazon, Microsoft ASICs) captured indirectly via QQQ/TQQQ — no clean US-listed
ETF exists for custom silicon yet. Flag as a known gap each report.
Holdings: SMH (both accounts). (SOXL exited 2026-07 — IRA leverage now via TQQQ/QLD.)
(What to monitor for this layer lives in the MONITORING MAP section below —
one canonical list across all layers.)

#### Layer 1 Kill Signal — AS-1 ASIC Substitution — CHECK EVERY REPORT
Same CLEAR / APPROACHING / TRIGGERED discipline and proximity quantification
as the memory kill signals; reported in the same kill-signal table.

  AS-1: NVIDIA data-center revenue growth <20% YoY, OR revenue QoQ negative
        for 2 consecutive quarters
        (tracks: merchant-GPU demand as hyperscaler custom silicon — Google
         TPU, Amazon Trainium, Microsoft Maia — displaces NVIDIA/AMD GPUs.
         ASIC = application-specific integrated circuit, a chip built for one
         workload; hyperscalers design their own to escape NVIDIA margins.
         This is the COMPUTE layer's kill signal: SMH is ~20% NVIDIA. The
         memory thesis is deliberately NOT covered here — every ASIC still
         needs HBM, so Layer 2 is ASIC-agnostic. Partial in-ETF hedge:
         Broadcom (~8% of SMH) co-designs hyperscaler ASICs and wins from the
         shift. QoQ leg tracked numerically in signal state, same machinery
         as KS-1/KS-4.)

### Layer 2 — Memory Bandwidth — HIGHEST CONVICTION
Thesis: Binding AI constraint is memory bandwidth, not compute FLOPS. Context
window explosion (8K to 1M tokens = 125x KV cache growth) plus HBM 3-to-1
wafer trade-off create structural supply tightness through 2027. DRAM oligopoly
(Samsung 36%, SK Hynix 32%, Micron 22%) on take-or-pay LTAs with hyperscalers.
Profitability inversion: commodity DRAM OPM 70-80% exceeds HBM OPM 50-60% —
not seen in 30 years. Memory trading at ~8x forward vs 25-35x peer semis.
Holdings: DRAM (both accounts) — SK Hynix 25.4% + Samsung 23.64% + MU 24.17%
          EWY — Korea proxy, SK Hynix + Samsung = ~45% of EWY weight

#### Memory Kill Signals — CHECK EVERY REPORT
Flag each as: CLEAR / APPROACHING / TRIGGERED

Each signal carries a plain-language "tracks:" gloss so the report is readable
without memorizing the KS-n codes. ALWAYS spell out what a signal tracks in the
report — never present a bare "KS-3" with no explanation.

  KS-1: DRAM spot price -10% for 3 consecutive months
        (tracks: spot price of commodity DRAM chips — the core memory product)
  KS-2: 2+ hyperscalers guide CapEx growth <10% same quarter
        (tracks: AI datacenter spending by Microsoft/Google/Amazon/Meta — the
         demand engine behind memory. Each name's latest guide % is tracked
         numerically in signal state; the script counts the kill condition.
         The daily gets an escalation search the morning after any of these
         names — or NVDA, for AS-1 — reports earnings.)
  KS-3: CXMT wafer output >400K WPM + HBM yield >50%
        (tracks: China's state-backed DRAM maker CXMT flooding the market with
         new supply — the main "China breaks the oligopoly" risk.
         WPM = wafers per month; HBM = high-bandwidth memory)
  KS-4: Server DDR5 price -10% QoQ for 2 consecutive quarters
        (tracks: the contract — not spot — price hyperscalers actually pay for
         server memory modules under multi-quarter take-or-pay deals)
  KS-5: Samsung or SK Hynix DRAM segment OPM drops below 60%
        (tracks: operating profit margin of the memory makers' DRAM business —
         how profitable / how intact the oligopoly's pricing power is.
         OPM = operating profit margin)
  KS-W: Helium spot >$300/Mcf (Iran conflict — Korean fab supply chain risk)
        (tracks: helium spot price — a fab input vulnerable to Iran conflict; a
         spike signals Korean fab supply-chain stress)

  QUANTIFY PROXIMITY every report. Don't just say CLEAR — say how far from
  trigger, using whatever current value web search returns. Express as
  "% of kill" (current ÷ trigger threshold) and/or absolute distance. Examples:
    KS-W: helium $144.58 vs $300 trigger = 48% of kill (CLEAR, lots of room)
    KS-5: SK Hynix DRAM OPM 72% vs 60% floor = 12 pts above trigger (CLEAR)
    KS-1: DRAM spot -3% MoM, month 1 of 3 needed at -10% = far from trigger
  The numeric distance is what makes APPROACHING meaningful. State the number,
  not a vibe. TRIGGERED = the full kill condition is satisfied.

#### APPROACHING Tripwire Thresholds — TUNABLE (edit these freely)
These per-signal thresholds define the line between CLEAR and APPROACHING. They
are the control dial for the two-tier system:
  → DAILY watchdog reads them to decide whether to escalate (alert) or stay
    quiet — a signal at/past its tripwire is what makes the daily "shout".
  → WEEKLY brief uses them to rank which signal is closest to firing.
Tighten a tripwire to get earlier warnings (noisier daily); loosen it for fewer
alerts (quieter daily). Each line is: TRIGGER (kill) | APPROACHING (tripwire).

  KS-1 DRAM spot   | −10% MoM ×3 consecutive months | ANY single month ≤ −10%
                     (1 of 3 met), OR latest month ≤ −7%
  KS-2 hypersc capex| 2+ hyperscalers guide CapEx growth <10% same Q
                     | ANY 1 hyperscaler guides <10%, OR any guide in 10–13%
  KS-3 CXMT        | >400K WPM AND HBM yield >50% | EITHER ≥80% of its line
                     (WPM >320K OR yield >40%)
  KS-4 server DDR5 | −10% QoQ ×2 consecutive quarters | ANY 1 quarter ≤ −10%
                     (1 of 2 met), OR latest quarter ≤ −7%
  KS-5 OPM         | Samsung OR SK Hynix DRAM OPM <60% | within 5 pts of floor
                     (either name's OPM <65%)
  KS-W helium      | >$300/Mcf | ≥80% of trigger (helium >$240/Mcf)
  AS-1 ASIC subst  | NVDA DC rev growth <20% YoY OR QoQ negative ×2
                     | YoY <35%, OR any single QoQ negative (1 of 2), OR a
                     top-4 hyperscaler starts selling its ASIC to external
                     customers at scale

  Iran exit tripwire (Section 3, CRAK — not a memory kill signal but
  the same daily/weekly logic):
  Brent exit       | Brent <$85 OR confirmed ceasefire | Brent within $7 of $85
                     (≤ $92), OR ceasefire MOU reached but unsigned (1 of 2)

  Defaults above are starting points — adjust the numbers, not the structure.
  If a signal's current value isn't available from search, mark "no fresh data"
  and report the last known reading rather than guessing.

### Layer 3 — Power / Grid — KNOWN GAP
Thesis: AI datacenter buildout outpacing grid capacity. Nuclear revival and
grid modernization are multi-year tailwinds independent of Iran conflict.
Current exposure: STARTER ONLY — small GRID position (taxable) added 2026-07.
Gap: Materially underweight vs thesis conviction; no nuclear/uranium exposure
(NLR/URNM/URA all unowned).
Agent instruction: Flag the remaining underweight in every report. Candidates
live in the
  Candidate / Watchlist Universe below and are fetched each run for live data.

### Layer 4 — Leveraged QQQ (TQQQ)
Tactical leverage-scaling layer. Also captures TPU/custom silicon indirectly
via GOOG and AMZN as top QQQ holdings. See TQQQ Strategy section.

---

## MONITORING MAP

The single canonical "what to watch" list across the whole AI-infrastructure
stack — demand at the top of the funnel down to power and networking at the
bottom. This replaces the old scattered per-layer "Monitor:" lines so there is
one source of truth. Organized by stack function, not by held position, so it
also seeds candidate generation across the full stack (not just energy).

  - Demand: AMZN/GOOG/MSFT/META/ORCL CapEx, AI cloud revenue, GPU/TPU cluster
    buildouts
  - Accelerators: NVIDIA GPU demand, AMD MI-series traction, Google TPU /
    Amazon Trainium / Microsoft Maia substitution risk
  - Memory: HBM3E/HBM4 allocation, Micron/SK Hynix/Samsung supply, DRAM/NAND
    spot + contract pricing
  - Foundry/packaging: TSMC 3nm/2nm capacity, CoWoS capacity, advanced
    packaging lead times
  - Networking: Broadcom/Marvell ASICs, Ethernet vs InfiniBand,
    optics/transceivers, Arista/Coherent/Lumentum signals
  - Data centers: power availability, grid interconnects, cooling, transformers,
    Vertiv/Eaton/Quanta backlog
  - Neo-clouds: Nebius/CoreWeave/Crusoe utilization, financing cost, customer
    concentration, GPU access
  - Risk signals (DAILY TRIPWIRE FEED): CapEx deceleration, inventory build,
    falling GPU/HBM lead times, memory price rollover, ASIC share gains, export
    controls. → This line is the early-warning watchlist the DAILY pulse leans
    on; the rest of the map is weekly-depth context.

Tiering:
  → WEEKLY (Opus) brief works the full map — every function gets a look when
    there is material news.
  → DAILY (Sonnet) pulse only needs the "Risk signals" line above plus the
    fast-moving kill-signal inputs; it does NOT walk the whole map each day.

Mandate note: several names here are individual stocks (Nebius, CoreWeave,
Crusoe, Vertiv, Eaton, Coherent, Lumentum), not ETFs. Under the current
ETF-only mandate they are monitoring CONTEXT only — the trade is still the ETF.
If/when the stock-first change lands, this map becomes the candidate-generation
source: name the stock, then map it to the ETF that holds it.

---

## CANDIDATE / WATCHLIST UNIVERSE

Unowned but thesis-relevant ETFs that fetch_data.py pulls every run (the
WATCHLIST list there). They are NOT holdings — they exist so the report can
surface dynamic "potential buys" with live price/RSI/volume data, primarily
to fill the standing Layer 3 power/grid gap.

  NLR  — nuclear energy                    (Layer 3 power/grid)
  URNM — uranium miners                    (Layer 3 power/grid)
  URA  — uranium / nuclear fuel            (Layer 3 power/grid)
  PAVE — US infrastructure buildout        (Layer 3 adjacency: grid + datacenter)
  NBIS — Nebius, neo-cloud / GPU capacity  (Neo-clouds — STOCK, not an ETF)
         First name added under the stock-first direction. Pure-play with no
         clean ETF wrapper, so it's watched directly. Until the full stock-first
         flip lands, treat as monitoring context: surface the NAME and its
         setup, and note which ETF (if any) gives indirect exposure, rather than
         issuing a buy on the bare stock. See the "never recommend underlying
         stock" rule below — NBIS is the flagged exception that motivates the
         pending mandate change.

How the agent uses them each report:
  → These are a POOL, not a fixed recommendation list. Each report selects and
    CYCLES 2–4 names to highlight as potential buys based on that day's
    conditions (RSI oversold, pullback from 52w high, volume spike) and any
    binary event/catalyst (nuclear policy, grid capex, uranium supply news).
  → Surfaced in two places: woven into Section 4 mapping as gap-fill
    candidates, and in the highlighted Potential Buys callout after Section 6.
  → Never presented as owned. Never recommend the underlying stock — the
    candidate ETF is the trade, same rule as holdings.
  → To reshape the pool, edit WATCHLIST in fetch_data.py and this list.

---

## TQQQ ROTATION STRATEGY

### Logic
Scale leverage based on how far QQQ is from its 52-week high. Be 3x leveraged
during meaningful pullbacks. Reduce to 1x near all-time highs. VIX confirms.

### Primary Signal: QQQ Drawdown from 52-Week ATH
Calculate every report:
  drawdown_pct = (QQQ_52w_high - QQQ_current_price) / QQQ_52w_high x 100

  Below 10%  = Near ATH. Favor QQQ (1x). Consider reducing TQQQ in IRA.
  10 to 20%  = Real pullback. TQQQ appropriate. Hold or add in IRA.
  Above 20%  = Deep correction. Full TQQQ conviction.

### Secondary Signal: VIX Confirmation
  VIX declining AND drawdown recovering toward below 10%
    = Rotate TQQQ to QQQ (IRA)
  VIX elevated or rising AND drawdown above 10%
    = Stay TQQQ, pullback is real
  VIX below 18 AND drawdown below 10%
    = Clearest rotate-to-QQQ signal

### Account-Specific Horizons

  TAXABLE (Account 1):
    → Rotation permitted but only on sustained multi-month signals
    → Do not act on weekly noise or single-day readings
    → Signal must persist 3-4 weeks before recommending action
    → Monthly rebalance horizon, not daily
    → All taxable TQQQ recommendations include:
       "Taxable: confirm signal over 3-4 weeks. Check hold period
        for long-term capital gains threshold."
    → Always note cost basis and estimated hold period

  IRA (Account 2):
    → Freely rotate TQQQ to QQQ based on signals
    → No tax consequence — act promptly
    → Time-sensitive rotation recommendations are IRA-first

### TQQQ Report Block Format
  QQQ: $X | 52w high: $X | Drawdown: X.X%
  VIX: X.X (rising / falling / flat)
  Signal: HOLD TQQQ / WATCH — approaching rotate / ROTATE to QQQ
  IRA action: [specific]
  Taxable action: [hold or sustained-signal note with weeks-confirmed flag]

---

## MACRO HEDGE POSITIONS
## Time-limited Iran conflict plays. Each has an explicit exit trigger.

| ETF  | Role                        | Exit Trigger                            |
|------|-----------------------------|-----------------------------------------|
| CRAK | Refining margins / Iran     | Ceasefire + crack spread normalization  |
| EWY  | Korea + memory thesis proxy | DO NOT exit on ceasefire — dual role    |

EXITED 2026-07 on the Iran EXIT signal: USO, XOP. CRAK stays
until its own trigger (ceasefire + crack spread normalization) fully lands.

EWY is the exception — serves as both Iran hedge AND memory thesis proxy.
Treat separately from pure conflict plays in every report.

---

## DATA SOURCES

### Market Data
Primary: yfinance via fetch_data.py (price, RSI, volume,
52w high). Runs at report generation time.

### News and Macro Intelligence
Agent should web search the following at report generation
time to supplement the price data:

  ALWAYS search (every report):
  - Iran conflict / Strait of Hormuz status
    → affects CRAK, EWY exit triggers (USO/XOP exited 2026-07)
  - DRAM/HBM spot pricing (TrendForce, DRAMeXchange)
    → kill signal KS-1 verification
  - Hyperscaler CapEx news (Microsoft, Google, Amazon, Meta)
    → kill signal KS-2 verification
  - Semiconductor sector news (NVDA, TSMC, SK Hynix, Samsung)
    → Layer 1 and Layer 2 thesis pulse

  SEARCH when relevant:
  - CXMT capacity / HBM yield news
    → kill signal KS-3 verification
  - Helium spot price
    → kill signal KS-W verification
  - Grid/power/nuclear news
    → Layer 3 gap context and Radar section candidates
  - NVIDIA data-center revenue / hyperscaler custom-silicon (TPU, Trainium,
    Maia) substitution news
    → kill signal AS-1 verification

### Bluesky Social Intelligence
NOT YET IMPLEMENTED — planned for a future version. The
unauthenticated Bluesky public AppView now sits behind bot
protection (HTTP 403), so this requires a Bluesky account
and an app password set via BSKY_HANDLE / BSKY_APP_PASSWORD
env vars. Until that is wired up, the agent should not
reference "Bluesky signals" in the report. Spec retained
here so the integration can be re-added cleanly.

Search Bluesky for signal, not noise. Use it to surface
fast-moving information that hasn't hit mainstream financial
news yet. Search the following:

  Macro / geopolitical (always):
  - Iran, Hormuz, ceasefire, oil supply
  - Relevant for: CRAK exit trigger monitoring

  AI infrastructure (always):
  - HBM, DRAM, memory bandwidth, AI infrastructure
  - Hyperscaler capex, data center power, nuclear AI
  - Relevant for: Layer 1-3 thesis pulse, Radar section

  Filter for signal:
  → Prioritize posts from known semiconductor analysts,
    energy reporters, geopolitical accounts
  → Ignore retail sentiment and price predictions
  → Only surface in report if it adds context not already
    covered by mainstream news search
  → Label clearly: "Bluesky signal: [source context]"
    so you know it's social intelligence, not verified news

### Source + Confidence Tagging
Every searched claim carries a tag: [source1, source2][confidence — basis].
This makes trust a first-class, scannable input — you size trades off this
report, so each line should say how much to trust it and what would change that.

  Format:  [Reuters, Bloomberg, TrendForce][high — multiple independent]
           [VideoCardz][med — single source, formal spec pending]
           [no source — inferred from price action][low]

  Confidence levels (DO NOT inflate — LLMs drift everything to "high"):
    high = 2+ independent reputable sources agree
    med  = single source, OR sources tracing to one origin, OR a reputable
           source on a still-developing / unconfirmed story
    low  = rumor, social chatter, unconfirmed, or own inference vs reporting
  Hard rules: a single-source claim is NEVER high. A tentative / unsigned /
  pending item (e.g. an unsigned MOU) is med at best. Always state the basis —
  it tells the reader what would upgrade or break the rating.
  Corroborate across 2+ independent outlets for any material/actionable claim.

### Counter-Argument Discipline
Every high-conviction / actionable call carries one specific, falsifiable
counter-argument — the concrete mechanism by which it could be wrong, tied to a
kill signal where one exists. This is structural protection against confirming
our own thesis. Applies to: Section 7 action items, Potential Buys picks, any
layer called INTACT, any kill signal called CLEAR with conviction.
  → No generic hedging ("risks remain, monitor closely") — name the failure mode.
  → "Breaks if KS-2 triggers (hyperscaler CapEx guides <10%)" is the standard.
  → If no credible counter exists, say so explicitly — that is itself signal.

### Data Freshness Rules
  - Market data: always from latest fetch_data.py run
  - If snapshot is stale (weekend/holiday): flag clearly
    at top of report as Section 1 does today
  - News search: run at generation time, not cached
  - Bluesky: run at generation time
  - If any source fails: note the gap, do not fabricate

---

## WEEKLY BRIEF STRUCTURE (Opus — `generate_brief.py`)

Full 9-section deep report. Runs the complete search sweep: every kill signal
searched, Iran/Hormuz, DRAM/HBM spot, hyperscaler CapEx, semis, power/grid.
Produces counter-arguments, company-by-company intelligence, Potential Buys
cycling, and the full Radar section. The weekly is the authoritative reference;
the daily is the exception-based watchdog between weeklies.

### Section 1 — TL;DR
5 bullets max. 30 seconds to read. Emoji signals throughout.
Top movers folded in here as the final 1-2 bullets if relevant.
Example format:
  • DRAM +0.9% on heavy volume — memory thesis holding, SK Hynix earnings beat
  • QQQ drawdown at 8.2% and falling — TQQQ rotate signal approaching for IRA
  • CRAK +2.1% — ceasefire talks stalled, refining premium intact
  • SMH under pressure — TSMC guidance cautious on 2H demand
  • Power/grid underweight: NLR +1.8% today, still unowned — note for watchlist

### 🔄 What Changed Since Last Report
Highlighted block, placed immediately after Section 1 (TL;DR) and before
Section 2. The point is DELTAS, not levels — what is different since the prior
session. Driven by the day-over-day delta data passed in the prompt plus any
thesis/news state changes found via search. 3–6 bullets, each a genuine change:
  → kill signal moving CLEAR→APPROACHING (with the proximity number)
  → an Iran exit trigger getting closer (Brent crossing toward $85, ceasefire
    progress)
  → RSI flipping into overbought/oversold, drawdown zone shift
  → a watchlist candidate pulling back into buy range
  → a fresh catalyst that wasn't in yesterday's report
Rules:
  → Do NOT restate today's absolute levels — that's the rest of the report.
  → If markets were closed between runs (prior session's bars == today's), say
    so and focus on news/thesis changes only.
  → If there is no prior snapshot on file, state that this is the first tracked
    run and there is no delta yet.

### Section 2 — TQQQ Signal Dashboard
  QQQ current price, 52-week high, drawdown %
  VIX level and direction
  Signal reading with emoji
  IRA action (specific)
  Taxable action (with multi-week confirmation note if actionable)

### Section 3 — Market and Macro Context
3-5 bullets only. Framing for the rest of the report.
Covers: broad market direction, Iran/conflict status, Fed/macro,
risk-on vs risk-off tone. Not a full section — just enough context.
Iran exit trigger check embedded here for CRAK (USO/XOP exited 2026-07). QUANTIFY distance to
each trigger using the current value from search, the same way kill signals do:
e.g. "Brent $91.12 vs $85 exit = $6.12 above trigger (HOLD)" or "ceasefire MOU
reached but unsigned — 1 of 2 exit conditions". State the number, not just HOLD.

### Section 4 — Company Intelligence + ETF Mapping
The core of the report. For each company with material news today:

  [COMPANY NAME] — [one paragraph on what happened and why it matters]
  Your exposure: [ETF (weight%)] | [ETF (weight%)] | [gap note if applicable]
  Top mover note if relevant: fold in here rather than separate section

Cover these companies when they have news. Skip if nothing material:
  Memory:    SK Hynix, Samsung, Micron
  Compute:   NVIDIA, TSMC, AMD, Broadcom
  Hyperscalers: Google, Amazon, Microsoft, Meta
  Other held: Tesla, Palantir, Roblox (brief, IRA/taxable equity context)
  Wildcard:  Any breaking name relevant to AI infra thesis
  EXCLUDE:   Apple — do NOT cover in company intelligence, even on breaking
             AI / DRAM-demand news (e.g. Siri/iPhone memory demand). It is a
             demand-side consumer name, not an infrastructure layer, and is not
             a tracked thesis name here. Omit it from the Section 4 Exposure
             Summary table and from any per-company detail block.

For each company, map to held ETFs at current weights.
If no held ETF covers a company well, flag the gap and suggest best-fit ETF.

### Section 5 — Kill-Signal Check (memory + Layer 1)
All 7 signals checked — KS-1 through KS-W (memory) plus AS-1 (Layer 1 ASIC
substitution). Render as a table with a plain-language column so the
report is readable without memorizing the KS-n codes:
  | Signal | What it tracks | Current | Tripwire | Kill | Status | Proximity |
  - Signal = the KS-n code plus a short name (e.g. "KS-3 CXMT ramp",
    "KS-5 DRAM margins").
  - What it tracks = one plain-English clause from the "tracks:" gloss in the
    Memory Kill Signals list. NEVER leave this blank — every row, including
    CLEAR ones, must say in plain language what the signal measures. Expand any
    acronym on first use (WPM = wafers/month, HBM = high-bandwidth memory,
    OPM = operating profit margin).
  - Current = the current value found via search (or "no fresh data" + last
    known reading).
  - Tripwire = the APPROACHING threshold; Kill = the full trigger condition.
  - Status = CLEAR / APPROACHING / TRIGGERED.
  - Proximity = the quantified distance ("48% of kill", "12 pts above 60%
    floor", "month 1 of 3") — never blank; if no data, write "no fresh data".

The table's "What it tracks", Status, and Proximity columns already carry the
plain-language meaning and the CLEAR/APPROACHING/TRIGGERED read for every
signal, so CLEAR signals need NO extra prose below the table — the row says it
all. Only APPROACHING or TRIGGERED signals get a full paragraph below the table:
why the reading sits there, what closes the remaining gap, and a falsifiable
counter-argument. Lead each paragraph with the signal code, short name, and
status, then a colon and the prose directly, e.g. "KS-3 CXMT ramp —
APPROACHING: ...". Do NOT prefix the prose with a meta-label like
"one paragraph:" or "context:" — write the explanation itself.

### Section 6 — Thesis Layer Status
One-line pulse per layer, then ETF dashboard table.

  Thesis pulse:
  Layer 1 Compute:      INTACT / WATCH / BROKEN
  Layer 2 Memory:       INTACT / WATCH / BROKEN
  Layer 3 Power/Grid:   STARTER — GRID held (small); underweight note + [NLR/URNM/URA/PAVE candidate]
  Layer 4 TQQQ:         [signal from Section 2]

  ETF Dashboard — all held ETFs:
  | Symbol | Price | Day % | RSI | 5d Trend | Vol vs 20d | Role | Signal |
  RSI below 30 = oversold, flag green as potential add
  RSI above 70 = overbought, flag red
  TQQQ and QLD: note leverage decay vs underlying index

### ⭐ Potential Buys — New Candidates
Highlighted block, placed immediately after Section 6. Surfaces dynamic buy
candidates from the Candidate / Watchlist Universe using their fetched data.
This is the "new potential buys" view and it CYCLES each report.

  Select 2–4 candidates based on that day's conditions and catalysts:
    → RSI oversold (<40 worth a look, <30 strong), pullback from 52w high,
      volume spike, or a binary event (nuclear policy, grid capex, uranium
      supply, infrastructure bill news).
  Render as a table:
  | Candidate | Price | Day % | RSI | % off 52w High | Why now | Thesis layer |
  Then one line each on the highlighted names (the catalyst/condition + which
  gap it fills — most will be the Layer 3 power/grid gap).

  Rules:
  → Pool only — never invent tickers outside the watchlist.
  → If nothing is compelling today, say so in one line; do not force picks.
  → Candidates are NOT held. Never present as owned. The ETF is the trade —
    never recommend the underlying stock.

### Section 7 — ETF Action Items
Concrete recommendations, ETFs only, account-labeled.
Format each as:
  [ETF] — [what to do and why]
  IRA: [specific action]
  Taxable: [action or "hold — confirm over 3-4 weeks" with LTCG note]

Power/grid gap reminder included here every report until position added.

### Section 8 — Upcoming Events
Next 7 days only. Relevant to held tickers only.
Format: Date | Event | Tickers affected | Why it matters

### Section 9 — Radar: Companies to Watch
Companies NOT currently in your portfolio that are relevant
to your AI infrastructure thesis. For each:

  [Company] — why it matters to the thesis right now
  Best ETF entry: [ETF (weight%)] — already owned or new
  If already owned via ETF: note the weight and whether
  current sizing is sufficient given the opportunity
  If not covered by any held ETF: flag as exposure gap
    with best-fit ETF candidate and approximate weight

Coverage priority:
  1. Memory adjacent: HBM suppliers, packaging (ASE, Amkor)
  2. Compute adjacent: CoWoS/advanced packaging, EUV (ASML)
  3. Power/grid: nuclear operators, transformer makers,
     grid software
  4. Networking: InfiniBand, Ethernet switching for AI clusters
  5. Any name generating significant AI infra news that week

Cap at 5 companies per report. Only include if there is a
genuine thesis-relevant reason that week — skip if nothing
material. Always map to an ETF. Never recommend buying
individual stocks directly.

---

## DAILY PULSE STRUCTURE (Sonnet — `daily_pulse.py`)

Lean tripwire check. NOT the full weekly brief. Its job is to (1) give a
20-second read on how held positions moved since the prior session, and
(2) check every kill signal + the Iran exit against the APPROACHING Tripwire
Thresholds, and SHOUT only if something crosses a tripwire or a holding moved
materially. On a quiet day it should be short and say so.

Do NOT reproduce the weekly's 9 sections, company-by-company intelligence,
Potential Buys cycling, or Radar — that all lives in the weekly Opus brief.

### Status Line
  # 🔔 Daily Pulse — YYYY-MM-DD
  ## Status: 🟢 ALL QUIET / 🟡 WATCH / 🔴 ALERT
  One line. Pick 🔴 ALERT if any signal is TRIGGERED; 🟡 WATCH if any signal
  is APPROACHING its tripwire OR a held position moved materially (≈ ±3% day,
  or RSI crossing 70/30); else 🟢 ALL QUIET. State the single most important
  reason.

### News TL;DR
  3–5 bullets, the day's most important headlines relevant to the thesis and
  held positions — a 20-second scan. Pull from the searches already run
  (Iran/Hormuz/oil, DRAM/HBM pricing, semis, hyperscaler CapEx) plus any major
  AI-infra or macro story. Each bullet: tight headline clause, ticker/layer it
  touches, [source(s)][confidence — basis] tag. Lead with whatever is most
  market-moving. Prioritize items that touch a kill signal, an Iran exit
  trigger, or a held ETF; skip generic noise. If genuinely nothing material
  broke today, say so in one line.

### Holdings Quick Read
  Tight table of HELD tickers only, using market data + delta:
  | Ticker | Price | Day % | RSI | Δ vs prior | Note |
  Flag RSI >70 (overbought) and <30 (oversold). Call out material movers.
  If markets were closed between runs (prior bars == today's), say so in one
  line and keep the table for reference.

### Kill-Signal Tripwire
  Table of all 7 kill signals (6 memory + AS-1 ASIC substitution), classified
  against the CLAUDE.md tripwire thresholds:
  | Signal | Current | Tripwire | Kill | Status | Proximity |
  Status = CLEAR / APPROACHING / TRIGGERED per the thresholds block.
  Proximity = quantified distance ("12 pts above 60% floor", "helium $145 vs
  $240 tripwire", "month 1 of 3").

  SEARCH BUDGET — run AT MOST 2 searches for this whole section, only for the
  fast-moving signals KS-1 (DRAM spot price) and KS-W (helium spot). EXCEPTION:
  on the morning after a MSFT/GOOG/AMZN/META earnings report the daily gets ONE
  extra authorized search for that name's CapEx guide (KS-2); after an NVDA
  report, one extra for data-center revenue (AS-1). The earnings calendar in
  signal state drives this. For the slower signals — KS-2 (hyperscaler CapEx),
  KS-3 (CXMT), KS-4 (server DDR5), KS-5 (DRAM OPM), AS-1 (NVDA DC revenue) —
  DO NOT run dedicated searches otherwise: reuse the last known
  reading and mark it "(last known)", unless a same-day headline already
  surfaced in News TL;DR moves one of them (classify off that headline, no
  extra search). If a value is unavailable, write "no fresh data" — never
  guess. The weekly Opus brief does the full per-signal search sweep; the daily
  only catches fast tripwire trips.

  Only signals that are APPROACHING or TRIGGERED get a one-line explanation
  below the table. CLEAR signals just sit in the table.

### Iran Exit Check
  One or two lines: Brent vs the $85 exit (quantify the gap) and Strait of
  Hormuz / ceasefire status, classified against the Iran tripwire in CLAUDE.md.
  Governs CRAK (USO/XOP exited 2026-07).

### TQQQ Drawdown
  One line: QQQ drawdown % from market data and which zone it implies
  (near-ATH 1x / pullback / deep correction). Note IRA rotation read in a few
  words only — the full account-specific logic is the weekly's job.

### ⚠️ Action (CONDITIONAL)
  Include ONLY if any kill signal is APPROACHING/TRIGGERED, the Iran exit is
  APPROACHING/TRIGGERED, or a holding moved materially. 2–4 bullets, ETF-level,
  naming the specific thing to watch or do and which signal drives it. If
  nothing crossed, OMIT this section entirely — do not pad.

### Daily Footer
  *AI-generated for research purposes only. Not financial advice. Do your own
  due diligence.*

### Daily-Specific Rules
  - Markdown only, ready to render. No code fences around the whole report. No
    preamble — first characters are the "# " title.
  - Use web search sparingly: Iran/Hormuz + Brent, DRAM/HBM spot (KS-1), and
    any major same-day headline that could move a kill signal. Do NOT run the
    full weekly search sweep.
  - Tag searched claims [source(s)][confidence — basis]; single-source is never
    "high", pending/unsigned never "high".
  - Prices come ONLY from the market data provided. Missing/stale → say so.
  - Keep it SHORT. A quiet day is a quick scan, not an essay.
  - ETF-level only for any action item.

---

## REPORT RULES

### Shared Rules (both tiers)
1. Action items nominate ETFs only, never individual stocks
2. Kill signals checked every report without exception, each with a QUANTIFIED
   proximity-to-trigger ("% of kill" / absolute gap) — never a bare CLEAR — and
   a plain-language "what it tracks" gloss with acronyms (WPM/HBM/OPM) expanded;
   never present a bare KS-n code with no explanation
3. Iran exit triggers also quantified — distance to Brent $85 / ceasefire state
4. EWY flagged as dual-role every report
5. Data source: yfinance via fetch_data.py — note if stale or missing
6. Searched claims carry [source(s)][confidence — basis] tags; single-source is
   never "high", pending/unsigned items never "high" — do not inflate confidence
7. Footer on every report: "AI-generated for research purposes only.
   Not financial advice. Do your own due diligence."

### Weekly-Only Rules
8. Company analysis is unrestricted — cover all holdings freely
9. Top movers folded into TL;DR and Company Intelligence, not standalone
10. TQQQ taxable actions require sustained multi-month signal confirmation
11. "What Changed Since Last Report" block (after TL;DR) leads with day-over-day
    deltas vs the prior archived session; never a restatement of today's levels
12. Power/grid gap flagged every weekly until position added or explicitly waived
13. Iran position (CRAK) always carries its exit trigger in Section 3
14. Leverage decay noted for TQQQ and QLD in ETF dashboard
15. Company-to-ETF weights web searched when a company is the day's focus
16. Potential Buys callout (after Section 6) cycles 2–4 watchlist candidates
    each report based on conditions/catalysts; candidates are never owned and
    the ETF is always the trade, never the underlying stock
17. High-conviction/actionable calls carry a specific, falsifiable counter-
    argument tied to a kill signal where one exists — no generic hedging

### Daily-Only Rules
18. Exception-based — SHOUT on tripwire crossings and material movers, stay
    short and quiet on normal days
19. Search budget capped: ≤2 dedicated searches (KS-1 DRAM spot + KS-W helium),
    +1 escalation search on the morning after a hyperscaler earnings report
    (KS-2) or an NVDA report (AS-1); other slower signals reuse last-known
    readings, not fresh searches
20. No company-by-company intelligence, Potential Buys cycling, or Radar —
    those are weekly-only sections
21. ⚠️ Action section included ONLY when something crossed a tripwire or moved
    materially; omitted entirely on quiet days

---

## FILES IN THIS PROJECT

  CLAUDE.md            — this file, agent instructions and thesis spec
  portfolio.md         — positions (GITIGNORED, personal) — spliced into the
                         prompt at generation time; copy portfolio.example.md
  fetch_data.py        — pulls price/RSI/volume for all tickers via yfinance
  generate_brief.py    — weekly Opus brief: Claude API call, report markdown
  daily_pulse.py       — daily Sonnet pulse: lean tripwire check
  send_email.py        — sends report via Gmail
  send_alert.py        — sends alert emails
  run.sh               — runs fetch + weekly brief + email in sequence
  run_daily.sh         — runs fetch + daily pulse + email
  run_weekly.sh        — runs fetch + weekly brief + email
  run_scheduled.sh     — scheduled execution wrapper
  output/              — generated reports (YYYY-MM-DD-brief.md, -daily.md)
  data/                — JSON snapshots from fetch_data.py
  data/history/        — archived daily snapshots (YYYY-MM-DD.json)
  data/signal_state.json — persistent kill-signal / Iran-exit / TQQQ state
                           (written by both tiers after each run; carries
                           classifications between runs so signals are not
                           re-guessed from scratch)

---

## HOW TO RUN

  python fetch_data.py        # pull fresh market data (both tiers need this)
  python generate_brief.py    # generate weekly Opus brief
  python daily_pulse.py       # generate daily Sonnet pulse
  python send_email.py        # deliver latest report via Gmail
  bash run_weekly.sh          # fetch + weekly brief + email
  bash run_daily.sh           # fetch + daily pulse + email
