"""
load_env.py — minimal .env loader (stdlib only, no python-dotenv dependency).

Reads KEY=VALUE lines from the project-root .env file into os.environ.
Values already present in the environment WIN — a shell export or the
launchd wrapper's sourced env always overrides the file, so .env is the
default and the shell is the escalation path.

Imported for its side effect by every entry-point script:
    import load_env  # noqa: F401
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def load(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip one layer of matching quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


load()
