"""Batman settings. Shared settings (index table, folders, calendar, holidays, lot sizes, price rules, Breeze limits,
costs, ENTRY_TIME / ENTRY_DTE / CHECK_TIME) come from shared/config.py and are re-exported here.

STATUS (11-Nov-2026): skeleton only. Decided with the user: entry like the condor (Monday 11:16, 43 DTE, next-month
expiry) and a time exit before expiry. Everything marked None is still to be agreed - no backtest runs until it is.
"""
import os
from pathlib import Path

from shared.config import *            # noqa: F401,F403  (shared settings, re-exported)
from shared.config import ROOT, OUTPUT_ROOT

STRATEGY   = "batman"
OUTPUT_DIR = OUTPUT_ROOT / STRATEGY                              # output/batman/
REF_DIR    = Path(os.environ.get("BATMAN_REF_DIR", ROOT / "data" / STRATEGY / "reference"))

# ---- decided ----
# Entry: Monday 11:16 at ENTRY_DTE (43) days before the monthly expiry - the same entry dates as the iron condor,
# so its cached candles and trade list can be reused. One check a day at CHECK_TIME (15:16).
ENTRY_SOURCE = "iron_condor"      # take entry dates / expiries from the condor's trade list

# ---- to be finalised with the user (all None until agreed) ----
EXIT_DTE        = None   # time exit: last trading day on/before expiry - EXIT_DTE calendar days
CALL_BUY_DELTA  = None   # call side: buy 1 at this delta ...
CALL_SELL_DELTA = None   # ... sell 2 at this delta
PUT_BUY_DELTA   = None   # put side: buy 1 at this delta ...
PUT_SELL_DELTA  = None   # ... sell 2 at this delta
WING_WIDTH      = None   # far bought leg beyond the sold strikes (None = unhedged ratio; points)
TP_RULE         = None   # profit target (e.g. % of max profit or of debit/credit)
SL_RULE         = None   # stop-loss
ENTRY_FILTER    = None   # e.g. 10-day move / credit test, if any
LOTS            = 1
