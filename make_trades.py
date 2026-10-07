#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in ic/tradeset.py."""
from ic.cli import preset

preset()          # --hedge etc. -> settings, before ic.config loads
from ic.tradeset import main  # noqa: E402

if __name__ == "__main__":
    main()
