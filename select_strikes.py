#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in ic/strikes.py."""
from ic.cli import preset

preset()          # --strike-set / --hedge / --filter -> settings, before ic.config loads
from ic.strikes import main  # noqa: E402

if __name__ == "__main__":
    main()
