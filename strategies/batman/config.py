"""Batman settings. Shared settings (index table, folders, calendar, holidays, lot sizes, price rules, Breeze limits,
costs, ENTRY_TIME / ENTRY_DTE / CHECK_TIME) come from shared/config.py and are re-exported here.

STATUS (13-Nov-2026): two variants agreed (unhedged, hedged). 2021-26 only, static capital Rs 2.5L, nearest-delta strikes.
"""
import os
from pathlib import Path

from shared.config import *            # noqa: F401,F403  (shared settings, re-exported)
from shared.config import ROOT, OUTPUT_ROOT, DATA_DIR

STRATEGY   = "batman"
OUTPUT_DIR = OUTPUT_ROOT / STRATEGY                              # output/batman/
REF_DIR    = Path(os.environ.get("BATMAN_REF_DIR", ROOT / "data" / STRATEGY / "reference"))

# ---- variants (BATMAN_VARIANT=unhedged|hedged, or --variant on the scripts) ----
# unhedged (agreed 11-Nov-2026): per side buy 1 lot ~20 delta, sell 2 lots ~16 delta further out. One sold lot per side is
#   uncovered -> unlimited risk beyond the sold strikes.
# hedged (agreed 13-Nov-2026, StockMock screenshot of 13-Jul-2026): per side buy 1 lot ~30 delta, sell 2 lots 100 pts further
#   out, buy 1 lot 600 pts beyond the bought leg (= 500 pts beyond the sold strike) -> a broken-wing butterfly per side, the
#   loss is capped (about Rs 16.9k a lot in the sample month vs Rs 13.8k for the 400-pt condor). Tested first at 18 DTE.
VARIANTS = {
    "unhedged": dict(buy_delta=0.20, sell_delta=0.16, sell_offset=None, wing_offset=None, strike_set="b20_16"),
    "hedged":   dict(buy_delta=0.30, sell_delta=None, sell_offset=100,  wing_offset=600,  strike_set="h30_100_600"),
}
VARIANT        = os.environ.get("BATMAN_VARIANT", "unhedged").lower()
if VARIANT not in VARIANTS:
    raise SystemExit(f"Unknown Batman variant '{VARIANT}' (BATMAN_VARIANT / --variant). Known: {', '.join(VARIANTS)}")
_V             = VARIANTS[VARIANT]
ENTRY_SOURCE   = "iron_condor"   # entry Monday 11:16 at ENTRY_DTE (43) - same dates/expiries as the condor trade lists
BUY_DELTA      = _V["buy_delta"]       # bought leg (closer to the money), calls and puts
SELL_DELTA     = _V["sell_delta"]      # unhedged: sold legs at this delta (further out than the bought one)
SELL_OFFSET    = _V["sell_offset"]     # hedged: sold legs this many points further out than the bought leg
WING_OFFSET    = _V["wing_offset"]     # hedged: far bought leg this many points beyond the bought leg (None = no wing)
BUY_LOTS       = 1
SELL_LOTS      = 2
WING_LOTS      = 1
STRIKE_METHOD  = "black_scholes_11:16"   # delta from option and spot prices at 11:16, as strategies/iron_condor/strikes.py
# Exits, checked once a day at CHECK_TIME (15:16) on the whole position, entry day included; stop before target.
# Capital per Batman: STATIC Rs 2.5 lakh for the tests (user, 11-Nov-2026) -> target = stop = Rs 10,000 in every month.
# (A margin estimate scaled by NIFTY x lot, k = 0.159 from the StockMock sample, was considered and set aside for now.)
CAPITAL        = 250_000
TP_PCT_OF_CAPITAL = 4.0           # target: P&L >= 4% of CAPITAL
SL_PCT_OF_CAPITAL = 4.0           # stop:   P&L <= -4% of CAPITAL
TP_RS          = CAPITAL * TP_PCT_OF_CAPITAL / 100     # Rs 10,000
SL_RS          = CAPITAL * SL_PCT_OF_CAPITAL / 100     # Rs 10,000
EXIT_DTE       = int(os.environ.get("BATMAN_EXIT_DTE", 18))   # time exit: last trading day on/before expiry - 18 days
                                                             # (same as the condor; to be tested; --exit-dte per run)
ENTRY_FILTER   = None            # every month first; the condor's 10-day move filter is a later variant
PERIODS        = ["2021-26 (68 cycles)"]   # 2019-20 not tested yet (user, 11-Nov-2026)

# ---- files ----
# The 68 monthly cycles of 2021-26 = the condor's StockMock reference months + the Apr-2026 expiry (entry 16-Mar-2026).
CYCLE_FILES    = [ROOT / "data" / "iron_condor" / "reference" / "ic_reference_trades.csv",
                  ROOT / "data" / "iron_condor" / "reference" / "ic_trades_apr26.csv"]
STRIKE_SETS_DIR = DATA_DIR / STRATEGY / "strike_sets"          # strikes_<name>.csv from select_strikes.py
STRIKE_SET     = os.environ.get("BATMAN_STRIKE_SET", _V["strike_set"])  # b20_16 (unhedged) / h30_100_600 (hedged)
SEARCH_AROUND  = 3               # candidate strikes each side of the Black-Scholes estimate of each target strike
MAX_EXTEND_ROUNDS = 4            # widen the search while a target delta is not bracketed
