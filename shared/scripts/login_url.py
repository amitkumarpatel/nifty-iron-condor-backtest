#!/usr/bin/env python3
"""Print today's Breeze login URL (API key read from .env and URL-encoded).
Open it, log in, and copy the `apisession` value from the address bar into BREEZE_SESSION in .env."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repository root
from shared.breeze_client import login_url  # noqa: E402

if __name__ == "__main__":
    print(login_url())
