#!/bin/bash
# run_scheduled.sh — wrapper that launchd calls for the 6am ET auto-send.
#
# Why this exists instead of pointing launchd straight at a run script:
#   launchd (like cron) starts with a bare environment — it does NOT load your
#   shell profile. So we must explicitly:
#     1. load the API + Gmail secrets from ~/.config/market-report/env
#     2. put the miniconda python on PATH, since the run scripts call `python`
#   Then it hands off to the tier run script, which keeps its own
#   fetch->generate->send stop-on-failure logic.
#
# Usage:  run_scheduled.sh [run_script]
#   run_script defaults to ./run.sh (legacy single-tier behavior). The two-tier
#   launchd plists pass run_weekly.sh (Mondays) or run_daily.sh (Tue–Fri).

# Resolve the project directory from this script's own location — no
# hardcoded user paths, so the repo is portable.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Secrets: project .env is canonical (also read by the Python scripts via
# load_env.py). ~/.config/market-report/env kept as a legacy fallback.
set -a  # auto-export everything sourced below
if [ -f "$SCRIPT_DIR/.env" ]; then
    . "$SCRIPT_DIR/.env"
elif [ -f "$HOME/.config/market-report/env" ]; then
    . "$HOME/.config/market-report/env"
else
    echo "FATAL: no secrets found — create $SCRIPT_DIR/.env (see .env.example)." >&2
    exit 1
fi
set +a

# run.sh invokes `python` — make sure it resolves to the miniconda interpreter
# the pipeline was built and tested against.
export PATH="$HOME/opt/miniconda3/bin:$PATH"

cd "$SCRIPT_DIR" || {
    echo "FATAL: could not cd into project directory." >&2
    exit 1
}

# Which tier to run. Defaults to ./run.sh so the legacy single plist still works.
RUN_SCRIPT="${1:-./run.sh}"
case "$RUN_SCRIPT" in
    /*) : ;;                  # absolute path — use as-is
    *)  RUN_SCRIPT="./$RUN_SCRIPT" ;;   # bare name — resolve in project dir
esac

if [ ! -x "$RUN_SCRIPT" ]; then
    echo "FATAL: run script '$RUN_SCRIPT' not found or not executable." >&2
    exit 1
fi

echo "===== scheduled run $(date '+%Y-%m-%d %H:%M:%S %Z')  →  $RUN_SCRIPT ====="
exec "$RUN_SCRIPT"
