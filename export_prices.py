#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in ic/export.py."""
from ic.cli import preset

preset("IC_leg_prices")          # --strike-set / --hedge / --filter -> settings, before ic.config loads
from ic.export import main  # noqa: E402

if __name__ == "__main__":
    main()
