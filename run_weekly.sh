#!/bin/bash
# run_weekly.sh — WEEKLY tier: fetch → generate_brief (Opus) → send (brief).
#
# The deep 9-section brief. Runs Mondays via launchd. Same stop-on-failure
# logic as the original run.sh: each step must succeed before the next runs, so
# a failed fetch never produces a stale brief and a failed generate never sends
# an empty email.

set -u

cd "$(dirname "$0")" || {
    echo "FAILURE: could not change into the project directory." >&2
    exit 1
}

echo "==> [1/3] Fetching market data (fetch_data.py)…"
if ! python fetch_data.py; then
    echo >&2
    echo "FAILURE: fetch_data.py failed — aborting." >&2
    echo "         No brief was generated and no email was sent." >&2
    python send_alert.py --tier weekly --stage fetch_data.py || true
    exit 1
fi

echo "==> [2/3] Generating WEEKLY brief (generate_brief.py — Opus)…"
if ! python generate_brief.py; then
    echo >&2
    echo "FAILURE: generate_brief.py failed — aborting." >&2
    echo "         No email was sent." >&2
    python send_alert.py --tier weekly --stage generate_brief.py || true
    exit 1
fi

echo "==> [3/3] Sending weekly brief (send_email.py --kind brief)…"
if ! python send_email.py --kind brief; then
    echo >&2
    echo "FAILURE: send_email.py failed." >&2
    echo "         The brief was generated and saved, but delivery failed." >&2
    python send_alert.py --tier weekly --stage send_email.py \
        --message "brief generated + saved, but delivery failed" || true
    exit 1
fi

echo
echo "SUCCESS: weekly fetch → generate → send all completed."
