#!/usr/bin/env python3
"""Entry point - see README.md. Logic lives in ic/probe.py."""
from ic.cli import preset

preset()          # --symbol -> settings, before ic.config loads
from ic.probe import main  # noqa: E402

if __name__ == "__main__":
    main()
