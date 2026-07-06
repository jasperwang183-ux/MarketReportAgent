"""
send_alert.py — email the OWNER when a scheduled run fails.

The two-tier pipeline stops on the first failed step (fetch / generate / send)
and, by design, sends no report when that happens. The downside is silence: a
6am run that dies on an API outage or an empty credit balance just… doesn't
arrive, and you find out by noticing the missing email. This closes that gap by
firing a short alert so a failure pings you instead of vanishing.

Scope on purpose:
  • Sends to ALERT_RECIPIENT only (the owner) — NOT the full brief recipient
    list. The other readers should never see plumbing failures.
  • Reuses the same Gmail SMTP creds as send_email.py (GMAIL_ADDRESS /
    GMAIL_APP_PASSWORD). This means it can still alert on a *generate* failure
    (Anthropic API down / out of credits), since email auth is independent of
    the Anthropic API. It canNOT alert if the failure is Gmail SMTP itself —
    that's an accepted blind spot, partial coverage beats none.
  • Best-effort: if the alert send fails, it exits 0 anyway so it never masks
    the original failure's exit code in the run script.

Usage:
    python send_alert.py --tier daily --stage generate_brief.py
    (optionally appends the tail of the run log for context)
"""

import argparse
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import load_env  # noqa: F401 — pulls .env into os.environ

# Where failure alerts go. Owner only — intentionally NOT send_email.RECIPIENTS.
# Set ALERT_RECIPIENT in .env; falls back to GMAIL_ADDRESS (self-alert).
ALERT_RECIPIENT = os.environ.get("ALERT_RECIPIENT") or os.environ.get("GMAIL_ADDRESS", "")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

LOG_PATH = Path.home() / ".config" / "market-report" / "run.log"
LOG_TAIL_LINES = 25


def log_tail():
    """Return the last LOG_TAIL_LINES of the run log, for failure context."""
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(run log not readable)"
    return "\n".join(lines[-LOG_TAIL_LINES:]) if lines else "(run log empty)"


def main():
    parser = argparse.ArgumentParser(description="Email the owner on run failure.")
    parser.add_argument("--tier", default="?", help="weekly or daily")
    parser.add_argument("--stage", default="?",
                        help="which step failed, e.g. generate_brief.py")
    parser.add_argument("--message", default="",
                        help="optional extra context line")
    args = parser.parse_args()

    address = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not address or not password:
        # No creds → can't alert. Stay silent and DON'T fail the caller.
        print("send_alert: Gmail creds missing — cannot send alert.", file=sys.stderr)
        return 0
    if not ALERT_RECIPIENT:
        print("send_alert: ALERT_RECIPIENT not set — cannot send alert.",
              file=sys.stderr)
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    subject = f"⚠️ Market Report FAILED — {args.tier} tier @ {args.stage}"
    body = (
        f"The {args.tier} market-report run failed.\n\n"
        f"  When:  {now}\n"
        f"  Tier:  {args.tier}\n"
        f"  Stage: {args.stage}\n"
    )
    if args.message:
        body += f"  Note:  {args.message}\n"
    body += (
        "\nNo report was sent for this run.\n\n"
        "Most common causes:\n"
        "  - Anthropic API: out of credits or overloaded (generate stage)\n"
        "  - Gmail SMTP auth (send stage)\n"
        "  - yfinance fetch error (fetch stage)\n\n"
        f"--- last {LOG_TAIL_LINES} lines of run.log ---\n"
        f"{log_tail()}\n"
    )

    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = ALERT_RECIPIENT
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(address, password)
            smtp.send_message(msg)
        print(f"send_alert: failure alert sent to {ALERT_RECIPIENT}.", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — best-effort, never mask original failure
        print(f"send_alert: could not send alert ({type(exc).__name__}: {exc}).",
              file=sys.stderr)

    # Always succeed so the run script's original failure exit code is preserved.
    return 0


if __name__ == "__main__":
    sys.exit(main())
