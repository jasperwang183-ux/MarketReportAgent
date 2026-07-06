#!/bin/bash
# run_daily.sh — DAILY tier: fetch → daily_pulse (Sonnet) → send (daily).
#
# The lean daily pulse + kill-signal tripwire. Runs Tue–Fri via launchd. Same
# stop-on-failure logic as run.sh: a failed fetch never produces a stale pulse
# and a failed generate never sends an empty email.

set -u

cd "$(dirname "$0")" || {
    echo "FAILURE: could not change into the project directory." >&2
    exit 1
}

echo "==> [1/3] Fetching market data (fetch_data.py)…"
if ! python fetch_data.py; then
    echo >&2
    echo "FAILURE: fetch_data.py failed — aborting." >&2
    echo "         No pulse was generated and no email was sent." >&2
    python send_alert.py --tier daily --stage fetch_data.py || true
    exit 1
fi

echo "==> [2/3] Generating DAILY pulse (daily_pulse.py — Sonnet)…"
if ! python daily_pulse.py; then
    echo >&2
    echo "FAILURE: daily_pulse.py failed — aborting." >&2
    echo "         No email was sent." >&2
    python send_alert.py --tier daily --stage daily_pulse.py || true
    exit 1
fi

echo "==> [3/3] Sending daily pulse (send_email.py --kind daily)…"
if ! python send_email.py --kind daily; then
    echo >&2
    echo "FAILURE: send_email.py failed." >&2
    echo "         The pulse was generated and saved, but delivery failed." >&2
    python send_alert.py --tier daily --stage send_email.py \
        --message "pulse generated + saved, but delivery failed" || true
    exit 1
fi

echo
echo "SUCCESS: daily fetch → generate → send all completed."
