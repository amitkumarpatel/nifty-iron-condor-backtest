#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in strategies/iron_condor/downloader.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repository root
from strategies.iron_condor.cli import preset  # noqa: E402

preset()          # per-run options -> settings, before the config loads
from strategies.iron_condor.downloader import main  # noqa: E402

if __name__ == "__main__":
    main()
