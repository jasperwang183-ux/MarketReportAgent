"""
daily_pulse.py — Lean DAILY market pulse (Sonnet).

The cheap, fast tier of the two-tier system. Where generate_brief.py is the
WEEKLY deep brief (Opus, full 9 sections, candidate buys, counter-arguments),
this is the DAILY tripwire: a quick read on held positions plus the kill-signal
/ Iran-exit check, with conditional "shout vs stay quiet" logic.

Design:
  • Reuses the shared data helpers from generate_brief.py (snapshot load, market
    block, day-over-day delta, preamble strip) so the two tiers never drift on
    data shape — but has its OWN Sonnet call and its OWN lean prompt.
  • Reads the APPROACHING Tripwire Thresholds block in CLAUDE.md to decide each
    signal's CLEAR / APPROACHING / TRIGGERED status. Those thresholds are the
    tunable dial: tighten for earlier (noisier) alerts, loosen for quieter days.
  • Stays SILENT on a normal day (one-line "all quiet" heartbeat) and ESCALATES
    only when a signal hits its tripwire or a holding moves materially. This is
    the binary-event insurance that the weekly cadence would miss by up to a week.

Output: output/YYYY-MM-DD-daily.md (distinct from the weekly's -brief.md).
"""

from __future__ import annotations

import os
import sys
from datetime import date

import load_env  # noqa: F401 — pulls .env (ANTHROPIC_API_KEY etc.) into os.environ

# Reuse the weekly tier's data-shaping helpers so the two stay in lockstep on
# snapshot format. Importing is safe: generate_brief guards main() under
# __name__ == "__main__", so importing only defines functions/constants.
from generate_brief import (
    PROJECT_DIR,
    OUTPUT_DIR,
    WEB_TOOLS,
    HYPERSCALERS,
    die,
    earnings_escalations,
    load_snapshot,
    load_thesis,
    format_market_block,
    load_prior_snapshot,
    format_delta_block,
    _strip_preamble,
    load_signal_state,
    format_signal_state_block,
    update_tqqq_state,
    extract_model_signals,
    merge_model_signals,
    save_signal_state,
    strip_signal_block,
)

# Sonnet for the daily — a fraction of Opus cost and plenty for a quick read +
# threshold classification. The heavy synthesis (counter-arguments, stack-wide
# buy picks) stays in the weekly Opus brief. Sonnet 5: budget_tokens is REMOVED
# (400s) — thinking is adaptive with an effort hint instead. Intro pricing
# $2/$10 per MTok through 2026-08-31, then $3/$15 (same as the old 4.6 rate).
MODEL = "claude-sonnet-5"

# Effort bounds how much the daily thinks/works — the successor to the old
# THINK_BUDGET cap from the 2026-06-10 empty-brief incident. "medium" on
# Sonnet 5 ≈ "high" on Sonnet 4.6: right for a lean tripwire check. Raise to
# "high" only if tripwire classifications start getting sloppy.
EFFORT = "medium"

# max_tokens is a CEILING, not a reservation — we're billed only for tokens
# actually generated, so a high cap costs nothing on a quiet day and only buys
# headroom on heavy thinking/search days (the 2026-06-10 empty-brief incident
# was this ceiling being too tight). 16k (up from 12k on Sonnet 4.6) because
# Sonnet 5's new tokenizer counts ~30% more tokens for the same text — a 12k
# cap tuned for 4.6 is effectively tighter on 5. Streamed, so no timeout risk.
# The empty-output guard in main() remains the backstop.
MAX_TOKENS = 16000

# Daily runs FEWER searches than the weekly (only the fast-moving signals), so a
# lower continuation cap is fine. Logs have never hit even the weekly's 6.
MAX_CONTINUATIONS = 4


def build_escalation_block(due: list[str]) -> str:
    """Earnings-day escalation text for the daily prompt.

    `due` = EARNINGS_WATCH names whose stored earnings date is today/yesterday.
    Grants ONE extra authorized search per reporting name, scoped to the signal
    that name drives (hyperscalers → KS-2 CapEx guide, NVDA → AS-1 DC revenue).
    """
    if not due:
        return ""
    lines = ["EARNINGS-DAY ESCALATION (overrides the normal search budget):"]
    for name in due:
        if name == "NVDA":
            lines.append(
                f"- {name} just reported earnings. You are authorized ONE "
                "extra search for NVIDIA's data-center revenue (level, QoQ and "
                "YoY growth). Classify AS-1 off it and emit qoq_pct + quarter "
                "for AS-1 in your JSON block — do NOT mark AS-1 carried forward."
            )
        else:
            lines.append(
                f"- {name} just reported earnings. You are authorized ONE "
                "extra search for its CapEx guidance. Classify KS-2 off it and "
                "emit a guides entry for it in your JSON block — do NOT mark "
                "KS-2 carried forward."
            )
    return "\n".join(lines) + "\n"


def build_daily_prompt(thesis: str, market_block: str, today: str, delta_block: str = "", signal_block: str = "", escalation_block: str = "") -> str:
    return f"""You are the ETF Research Agent's DAILY PULSE — the fast, lean \
tier. This is NOT the full weekly brief. Produce a short daily pulse in \
markdown: a quick read on held positions plus the kill-signal / Iran-exit \
tripwire check, with conditional alerting.

Today's date: {today}

=== BEGIN CLAUDE.md (full thesis + portfolio + TRIPWIRE THRESHOLDS) ===
{thesis}
=== END CLAUDE.md ===

=== BEGIN MARKET DATA (from data/snapshot.json) ===
{market_block}
=== END MARKET DATA ===

=== BEGIN DAY-OVER-DAY DELTA (vs prior archived session) ===
{delta_block or "No prior snapshot on file — first tracked run, no delta yet."}
=== END DAY-OVER-DAY DELTA ===

=== BEGIN SIGNAL STATE (carry forward what you did not search) ===
{signal_block or "No signal state on file — first tracked run. Classify all kill signals and Iran exit from scratch based on your searches."}
=== END SIGNAL STATE ===

{escalation_block}SIGNAL STATE CARRY-FORWARD RULES:
You searched KS-1 (DRAM spot) and KS-W (helium) this run. For KS-2 through \
KS-5 and AS-1, carry forward the status and value from the SIGNAL STATE block \
above unless a headline you already surfaced in News TL;DR gives you reason to \
change the classification, or an EARNINGS-DAY ESCALATION above authorizes a \
dedicated search. In the JSON block at the end, set source to "carried \
forward" for any signal you did not search.

OUTPUT INSTRUCTIONS:
Follow the DAILY PULSE STRUCTURE section in the CLAUDE.md above EXACTLY — it \
is the single authoritative spec for this tier: section order (Status / News \
TL;DR / Holdings Quick Read / Kill-Signal Tripwire / Iran Exit Check / TQQQ \
Drawdown / conditional ⚠️ Action / footer), the ALERT/WATCH/QUIET status \
logic, the kill-signal table columns, the search budget and its earnings-day \
escalation exception, and the Daily-Specific Rules (18–21) plus Shared Rules \
(1–7) in REPORT RULES. Key mechanical reminders (also in the spec):
- Markdown only, no preamble — your very first characters must be \
"# 🔔 Daily Pulse — {today}". No code fences around the whole report.
- Prices come ONLY from the market data provided; missing/stale → say so.
- Quiet day = short. Omit ⚠️ Action entirely if nothing crossed a tripwire.
- SIGNAL STATE JSON BLOCK: After the disclaimer footer, on a new line, emit an \
invisible JSON block with your signal classifications. This block is machine- \
parsed by the script and stripped before the report is saved/emailed — the \
reader never sees it. Emit it EXACTLY in this format:

<!-- SIGNAL_STATE_JSON
{{"kill_signals": {{"KS-1": {{"status": "CLEAR", "value": "...", "mom_pct": -2.5, "month": "2026-06", "source": "...", "confidence": "...", "note": ""}}, "KS-2": {{"status": "...", "value": "...", "source": "carried forward", "confidence": "...", "note": ""}}, "KS-3": {{"status": "...", "value": "...", "source": "carried forward", "confidence": "...", "note": ""}}, "KS-4": {{"status": "...", "value": "...", "source": "carried forward", "confidence": "...", "note": ""}}, "KS-5": {{"status": "...", "value": "...", "source": "carried forward", "confidence": "...", "note": ""}}, "KS-W": {{"status": "...", "value": "...", "source": "...", "confidence": "...", "note": ""}}, "AS-1": {{"status": "...", "value": "...", "source": "carried forward", "confidence": "...", "note": ""}}}}, "iran_exit": {{"status": "HOLD", "brent": "...", "ceasefire_state": "...", "source": "...", "confidence": "..."}}}}
SIGNAL_STATE_JSON -->

Rules for the JSON block:
  - status: exactly one of CLEAR, APPROACHING, TRIGGERED (kill signals) or \
HOLD, APPROACHING, EXIT (Iran exit).
  - KS-1: since you searched DRAM spot, also emit "mom_pct" (latest \
month-over-month % change, as a NUMBER) and "month" ("YYYY-MM") when your \
search surfaced a numeric reading — the script tracks the month history and \
computes the 3-month streak itself. Omit both fields if no numeric reading.
  - For KS-2 through KS-5 and AS-1: carry forward from SIGNAL STATE block; set \
source to "carried forward". Exceptions: an EARNINGS-DAY ESCALATION above \
(emit "guides" {{"pct", "quarter"}} per reporting hyperscaler for KS-2, or \
"qoq_pct" + "quarter" for AS-1), or a same-day headline giving an actual new \
number.
  - Include ALL 7 kill signals (KS-1..KS-W + AS-1) and iran_exit.
  - The JSON must be valid — no trailing commas, no comments inside it.
"""


def call_claude(prompt: str) -> str:
    """Stream a Sonnet call with the server-side web tools, resuming on
    pause_turn. Mirrors the weekly tier's robust loop but on the daily model."""
    try:
        import anthropic
    except ImportError:
        die("anthropic SDK not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY is not set.\n"
            "    export ANTHROPIC_API_KEY=sk-ant-...\n"
            "Get a key at https://console.anthropic.com/settings/keys",
            file=sys.stderr,
        )
        sys.exit(2)

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": prompt}]

    resp = None
    container_id = None
    try:
        for _ in range(MAX_CONTINUATIONS):
            kwargs = {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": EFFORT},
                "tools": WEB_TOOLS,
                "messages": messages,
            }
            if container_id is not None:
                kwargs["container"] = container_id

            with client.messages.stream(**kwargs) as stream:
                resp = stream.get_final_message()

            container = getattr(resp, "container", None)
            if container is not None and getattr(container, "id", None):
                container_id = container.id

            if resp.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": resp.content})
        else:
            print(
                "WARNING: hit MAX_CONTINUATIONS while resuming web-search turns; "
                "daily pulse may be incomplete.",
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
            "WARNING: daily pulse hit max_tokens — may be truncated. "
            f"Consider raising MAX_TOKENS (currently {MAX_TOKENS}).",
            file=sys.stderr,
        )

    parts = [block.text for block in resp.content if getattr(block, "type", None) == "text"]
    return _strip_preamble("\n".join(parts).strip())


def main() -> int:
    snap = load_snapshot()
    thesis = load_thesis()
    market_block = format_market_block(snap)

    prior = load_prior_snapshot(snap)
    delta_block = format_delta_block(snap, prior)
    if prior:
        print(
            f"Daily delta vs prior session {prior.get('generated_at_utc', '?')[:10]}.",
            file=sys.stderr,
        )
    else:
        print("No prior snapshot found — first tracked run, no delta.", file=sys.stderr)

    # Signal state: read prior run's classifications.
    signal_state = load_signal_state()
    today = date.today().isoformat()
    signal_block = format_signal_state_block(signal_state, today)

    # Earnings-day escalation: a reporting hyperscaler authorizes a KS-2
    # search; NVDA authorizes AS-1. Grants the merge write-authority too.
    due = earnings_escalations(signal_state, today)
    extra_searched = set()
    if any(n in HYPERSCALERS for n in due):
        extra_searched.add("KS-2")
    if "NVDA" in due:
        extra_searched.add("AS-1")
    if due:
        print(f"Earnings escalation active for: {', '.join(due)} "
              f"(extra search authority: {', '.join(sorted(extra_searched))})",
              file=sys.stderr)

    prompt = build_daily_prompt(thesis, market_block, today, delta_block,
                                signal_block, build_escalation_block(due))

    print(f"Generating daily pulse for {today} via {MODEL}…", file=sys.stderr)
    report = call_claude(prompt)

    # Empty-output guard. If the model produced no usable text (e.g. it spent the
    # whole token budget on thinking/search and hit max_tokens before emitting the
    # report), do NOT save a blank file and do NOT let the pipeline email it.
    # die() exits non-zero so run_daily.sh aborts before send_email.py runs —
    # a loud failure instead of the silent 1-byte email of 2026-06-10.
    if not report or not report.strip():
        die(
            "Daily pulse came back EMPTY — nothing saved, nothing sent. The model "
            "likely exhausted MAX_TOKENS on thinking/search before writing any "
            f"report text (MAX_TOKENS={MAX_TOKENS}). Raise it or retry."
        )

    # Signal state: write back (TQQQ zone + model classifications).
    update_tqqq_state(signal_state, snap, today, "daily")
    model_data = extract_model_signals(report)
    if model_data:
        merge_model_signals(signal_state, model_data, today, "daily",
                            extra_searched=extra_searched)
    else:
        print("WARNING: could not extract signal state from model output; "
              "state file unchanged for kill signals / Iran exit.",
              file=sys.stderr)
    signal_state["last_daily_run"] = today
    save_signal_state(signal_state)

    # Strip the hidden JSON block before saving the reader-facing report.
    report = strip_signal_block(report)

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        die(f"Could not create output dir {OUTPUT_DIR}: {exc}")

    out_path = OUTPUT_DIR / f"{today}-daily.md"
    out_path.write_text(report)

    print()
    print(report)
    print()
    print(f"Saved to {out_path.relative_to(PROJECT_DIR)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
