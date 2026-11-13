#!/usr/bin/env python3
"""Entry point - logic lives in strategies/batman/engine.py. Run from the repository root.
--variant unhedged|hedged (default unhedged) picks the Batman variant (= BATMAN_VARIANT)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))   # repository root
if "--variant" in sys.argv:                                      # before the config loads
    i = sys.argv.index("--variant")
    os.environ["BATMAN_VARIANT"] = sys.argv[i + 1]
    del sys.argv[i:i + 2]
from strategies.batman.engine import main  # noqa: E402

if __name__ == "__main__":
    main()
