#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in shared/nse_index.py (NIFTY / BANKNIFTY / India VIX official closes)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # repository root
from shared.nse_index import main  # noqa: E402

if __name__ == "__main__":
    main()
