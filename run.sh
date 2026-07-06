#!/bin/bash
# run.sh — run the full ETF brief pipeline in sequence: fetch → generate → send.
#
# Each step must succeed before the next runs:
#   1. fetch_data.py   — pull fresh market data
#   2. generate_brief.py — build today's report (only if fetch succeeded)
#   3. send_email.py   — deliver the report (only if generate succeeded)
#
# If any step fails the script stops immediately and nothing downstream runs,
# so a failed fetch never produces a stale brief and a failed generate never
# sends an empty email.

set -u

# Always run from the project directory (where this script lives), so the
# pipeline works regardless of the caller's current directory.
cd "$(dirname "$0")" || {
    echo "FAILURE: could not change into the project directory." >&2
    exit 1
}

echo "==> [1/3] Fetching market data (fetch_data.py)…"
if ! python fetch_data.py; then
    echo >&2
    echo "FAILURE: fetch_data.py failed — aborting." >&2
    echo "         No brief was generated and no email was sent." >&2
    exit 1
fi

echo "==> [2/3] Generating brief (generate_brief.py)…"
if ! python generate_brief.py; then
    echo >&2
    echo "FAILURE: generate_brief.py failed — aborting." >&2
    echo "         No email was sent." >&2
    exit 1
fi

echo "==> [3/3] Sending email (send_email.py)…"
if ! python send_email.py; then
    echo >&2
    echo "FAILURE: send_email.py failed." >&2
    echo "         The brief was generated and saved, but delivery failed." >&2
    exit 1
fi

echo
echo "SUCCESS: fetch → generate → send all completed."
