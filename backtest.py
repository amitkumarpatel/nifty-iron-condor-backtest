#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in ic/engine.py."""
from ic.cli import preset

preset("IC_backtest")          # --strike-set / --hedge / --filter -> settings, before ic.config loads
from ic.engine import main  # noqa: E402

if __name__ == "__main__":
    main()
