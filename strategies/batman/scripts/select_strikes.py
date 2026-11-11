#!/usr/bin/env python3
"""Entry point - logic lives in strategies/batman/strikes.py. Run from the repository root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repository root
from strategies.batman.strikes import main  # noqa: E402

if __name__ == "__main__":
    main()
