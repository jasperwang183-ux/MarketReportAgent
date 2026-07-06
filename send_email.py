"""
send_email.py — deliver the latest pre-market brief via Gmail SMTP.

Reads the most recent report from output/, builds a plain-text email,
and auto-sends to every address in RECIPIENTS using Gmail SMTP+STARTTLS.

Configuration comes from environment variables (set in .env at the project
root, or exported in the shell — the shell wins):
    GMAIL_ADDRESS         sender account, e.g. you@gmail.com
    GMAIL_APP_PASSWORD    16-char Gmail app password (2FA must be on)
    RECIPIENTS            comma-separated list of report recipients
"""

import argparse
import os
import re
import sys
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import load_env  # noqa: F401 — pulls .env into os.environ

# Who receives the brief: RECIPIENTS in .env, comma-separated.
RECIPIENTS = [
    addr.strip()
    for addr in os.environ.get("RECIPIENTS", "").split(",")
    if addr.strip()
]

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# The two report tiers. Each writes its own filename suffix and carries its own
# email subject prefix + the heading its one-line subject snippet is pulled from.
#   brief = weekly Opus deep brief (generate_brief.py → -brief.md)
#   daily = daily Sonnet pulse     (daily_pulse.py    → -daily.md)
KINDS = {
    "brief": {
        "regex": re.compile(r"^(\d{4}-\d{2}-\d{2})-brief\.md$"),
        "subject_prefix": "Morning Brief",
        "snippet_heading": "TL;DR",
    },
    "daily": {
        "regex": re.compile(r"^(\d{4}-\d{2}-\d{2})-daily\.md$"),
        "subject_prefix": "Daily Pulse",
        "snippet_heading": "Status",
    },
}


def find_latest_report(name_re):
    """Return (date_str, Path) for the newest file matching name_re, or None."""
    if not OUTPUT_DIR.exists():
        return None
    candidates = []
    for entry in OUTPUT_DIR.iterdir():
        m = name_re.match(entry.name)
        if m and entry.is_file():
            candidates.append((m.group(1), entry))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def _clean_snippet(text):
    """Strip markdown/emoji from a heading-derived subject snippet."""
    # Drop leading emoji/bullet + space (e.g., "🟢 ", "- ")
    text = re.sub(r"^[^\w\"'(\[]+\s*", "", text)
    # Strip markdown bold/italic markers
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    text = re.sub(r"(?<!_)_(?!_)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 140:
        text = text[:137].rstrip() + "..."
    return text


def extract_subject_snippet(report_text, heading):
    """Pull a one-line subject snippet from under the given heading.

    For the weekly brief (heading "TL;DR") this is the first bullet. For the
    daily pulse (heading "Status") the headline is the heading's own text after
    the colon (e.g. "## Status: 🔴 ALERT — KS-5 ...") or, failing that, the first
    non-empty line beneath it. Returns "" if nothing usable is found.
    """
    lines = report_text.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##") and heading in stripped:
            in_section = True
            # Daily "## Status: <text>" carries the headline inline after the
            # colon — use it directly when present.
            after = stripped.split(heading, 1)[1].lstrip(": ").strip()
            if after:
                return _clean_snippet(after)
            continue
        if in_section:
            if stripped.startswith("##"):
                break
            if stripped.startswith(("-", "*", "+")):
                return _clean_snippet(stripped[1:].strip())
            if stripped:  # first non-empty prose line (daily fallback)
                return _clean_snippet(stripped)
    return ""


def require_env():
    """Return (address, password) or print setup instructions and exit."""
    address = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    missing = [k for k, v in (("GMAIL_ADDRESS", address),
                              ("GMAIL_APP_PASSWORD", password)) if not v]
    if missing:
        print("ERROR: missing required environment variables: "
              + ", ".join(missing))
        print()
        print("Set them in .env at the project root (see .env.example):")
        print('    GMAIL_ADDRESS="you@gmail.com"')
        print('    GMAIL_APP_PASSWORD="your-16-char-app-password"')
        print()
        print("Or export the same variables in your shell / ~/.zshrc.")
        print()
        print("Generate an app password at: https://myaccount.google.com/apppasswords")
        print("(2-Step Verification must be enabled on the account.)")
        sys.exit(1)
    return address, password


# Inline CSS for the HTML email. A <style> block (rather than per-cell inline
# styles) keeps the payload small and renders correctly in Gmail web/app.
EMAIL_CSS = """
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         font-size: 14px; line-height: 1.5; color: #1a1a1a;
         max-width: 900px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 22px; margin: 0 0 12px; }
  h2 { font-size: 18px; margin-top: 28px; border-bottom: 1px solid #e0e0e0;
       padding-bottom: 4px; }
  h3 { font-size: 15px; margin-top: 20px; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }
  th, td { border: 1px solid #d0d0d0; padding: 6px 10px; text-align: left;
           vertical-align: top; }
  th { background: #f4f6f8; font-weight: 600; }
  tr:nth-child(even) td { background: #fafbfc; }
  code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px;
         font-family: SFMono-Regular, Consolas, "Liberation Mono", monospace; }
  hr { border: none; border-top: 1px solid #e0e0e0; margin: 24px 0; }
  em { color: #555; }
"""


def render_html(report_text):
    """Convert the markdown report to styled HTML for the email's rich part.

    Returns None if the optional `markdown` package isn't installed, in which
    case the caller falls back to the plain-text body alone.
    """
    try:
        import markdown
    except ImportError:
        return None
    body = markdown.markdown(
        report_text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<style>{EMAIL_CSS}</style></head><body>{body}</body></html>"
    )


def build_message(date_str, report_text, recipient, sender,
                  subject_prefix, snippet_heading):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    snippet = extract_subject_snippet(report_text, snippet_heading)
    if snippet:
        msg["Subject"] = f"{subject_prefix} — {date_str} | {snippet}"
    else:
        msg["Subject"] = f"{subject_prefix} — {date_str}"
    # Plain text stays as the fallback part; HTML (if available) renders the
    # markdown tables as real bordered tables in Gmail.
    msg.set_content(report_text)
    html = render_html(report_text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def main():
    parser = argparse.ArgumentParser(description="Email the latest report.")
    parser.add_argument(
        "--kind", choices=sorted(KINDS), default="brief",
        help="Which tier to send: 'brief' (weekly Opus) or 'daily' (Sonnet "
             "pulse). Defaults to 'brief' for backward compatibility.",
    )
    args = parser.parse_args()
    kind = KINDS[args.kind]

    latest = find_latest_report(kind["regex"])
    if latest is None:
        gen = "daily_pulse.py" if args.kind == "daily" else "generate_brief.py"
        print(f"ERROR: no '{args.kind}' report files found in {OUTPUT_DIR}")
        print(f"Run `python {gen}` first to produce today's {args.kind}.")
        sys.exit(1)
    date_str, report_path = latest
    report_text = report_path.read_text(encoding="utf-8")
    print(f"Using report: {report_path.name}  (kind={args.kind})")

    if render_html(report_text) is None:
        print("  note: `markdown` package not installed — sending plain text only.")
        print("        for nicely rendered tables in Gmail: pip install markdown")

    if not RECIPIENTS:
        print("ERROR: RECIPIENTS is empty — set it in .env as a "
              "comma-separated list (see .env.example).")
        sys.exit(1)

    address, password = require_env()

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            try:
                smtp.login(address, password)
            except smtplib.SMTPAuthenticationError as e:
                print("ERROR: Gmail SMTP authentication failed.")
                print(f"Server said: {e.smtp_code} {e.smtp_error!r}")
                print()
                print("Check that:")
                print("  - GMAIL_ADDRESS matches the account that issued the app password")
                print("  - GMAIL_APP_PASSWORD is the 16-character app password "
                      "(not your normal login password)")
                print("  - 2-Step Verification is enabled on the Google account")
                print("  - Generate a fresh app password if needed: "
                      "https://myaccount.google.com/apppasswords")
                sys.exit(1)

            sent, failed = [], []
            for recipient in RECIPIENTS:
                try:
                    msg = build_message(date_str, report_text, recipient, address,
                                        kind["subject_prefix"], kind["snippet_heading"])
                    smtp.send_message(msg)
                    sent.append(recipient)
                except Exception as e:
                    failed.append((recipient, str(e)))
                    print(f"  ! Failed to send to {recipient}: {e}")
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected,
            OSError) as e:
        print(f"ERROR: could not reach Gmail SMTP ({SMTP_SERVER}:{SMTP_PORT}): {e}")
        sys.exit(1)

    print()
    print(f"Sent Morning Brief to {len(sent)} recipient{'s' if len(sent) != 1 else ''}:")
    for r in sent:
        print(f"  - {r}")
    if failed:
        print()
        print(f"Failed for {len(failed)} recipient(s):")
        for r, err in failed:
            print(f"  - {r}: {err}")
        sys.exit(2)


if __name__ == "__main__":
    main()
