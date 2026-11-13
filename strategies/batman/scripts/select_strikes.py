#!/usr/bin/env python3
"""Entry point - logic lives in strategies/batman/strikes.py. Run from the repository root.
--variant unhedged|hedged (default unhedged) picks the Batman variant (= BATMAN_VARIANT)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repository root
if "--variant" in sys.argv:                                      # before the config loads
    i = sys.argv.index("--variant")
    os.environ["BATMAN_VARIANT"] = sys.argv[i + 1]
    del sys.argv[i:i + 2]
if "--capital" in sys.argv:                                      # margin (default) | static
    i = sys.argv.index("--capital")
    os.environ["BATMAN_CAPITAL"] = sys.argv[i + 1]
    del sys.argv[i:i + 2]
from strategies.batman.strikes import main  # noqa: E402

if __name__ == "__main__":
    main()
