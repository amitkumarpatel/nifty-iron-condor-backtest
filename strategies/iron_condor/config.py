"""Iron condor settings: trade lists, rules, forward-test rule set, strike sets, fallback, reconciliation.
Everything shared by all strategies (index table, folders, calendar, holidays, lot sizes, price rules, Breeze limits,
costs, entry/check times) comes from shared/config.py and is re-exported here, so `C.<NAME>` works for both."""
import os
from pathlib import Path

from shared.config import *            # noqa: F401,F403  (shared settings, re-exported)
from shared.config import _IDX, ROOT, INDEX, FILE_PREFIX, DATA_DIR, OUTPUT_ROOT

STRATEGY     = "iron_condor"
# ---- folders & files (IC_REF_DIR overrides the reference folder; used by the smoke test) ----
OUTPUT_DIR   = OUTPUT_ROOT / STRATEGY                     # output/iron_condor/
REF_DIR      = Path(os.environ.get("IC_REF_DIR", ROOT / "data" / STRATEGY / "reference"))
# Trade set: "" = the StockMock reference trades; IC_TRADE_SET=<name> (or --trade-set) = a generated set
# (make_trades.py) in ic_trades_<name>.csv / ic_legs_<name>.csv, e.g. years StockMock never ran.
TRADE_SET    = os.environ.get("IC_TRADE_SET", "")
TRADES_CSV   = REF_DIR / (FILE_PREFIX + (f"ic_trades_{TRADE_SET}.csv" if TRADE_SET else "ic_reference_trades.csv"))
LEGS_CSV     = REF_DIR / (FILE_PREFIX + (f"ic_legs_{TRADE_SET}.csv" if TRADE_SET else "ic_reference_legs.csv"))
REPORT_XLSX  = OUTPUT_DIR / (FILE_PREFIX.upper() + "IC_backtest_report.xlsx")
PROBE_DIR    = OUTPUT_DIR / ("probe" if INDEX == "NIFTY" else f"probe_{INDEX.lower()}")

# ---- strategy rules (ENTRY_TIME, ENTRY_DTE, EXPIRY_WEEKDAY and CHECK_TIME are in shared/config.py) ----

# ---- forward-test rule set (adopted 10-Oct-2026; wide condor 400 pts from 18-Oct-2026; README section 1b) ----
# Used by the forward-test skill (.claude/skills/nifty-ic-forward-test). backtest.py does NOT use these:
# its defaults below stay the earlier rule (300-pt hedges, skip beyond +/-2.5%), kept as the comparison.
# The credit test is always made on the SIGNAL condor (hedges FWD_SIGNAL_WIDTH points out), whatever is traded:
#   10-day move <= FWD_WIDE_MOVE_PCT and signal credit >= FWD_WIDE_MIN_CREDIT_PCT of the signal width
#       -> wide condor (FWD_WIDE_WIDTHS; one paper trade per width if more than one is listed),
#          profit target FWD_WIDE_TP_FRACTION
#   else 10-day move <= FWD_NARROW_MOVE_PCT and signal credit >= FWD_MIN_CREDIT_PCT
#       -> normal condor (HEDGE_WIDTH), profit target TP_FRACTION
#   else skip the month. Stop-loss, daily check and time exit are the same for all.
FWD_SIGNAL_WIDTH        = 400     # points: the condor whose credit decides (180 / 160 points)
FWD_WIDE_WIDTHS         = [400]   # traded when credit is rich: "variant 3". The user switched back from 600 on 18-Oct-2026 to keep
                                  # the maximum loss near 2-3% of the account; review after 6-12 months (e.g. [400, 600] to log both).
FWD_WIDE_MOVE_PCT       = 2.0     # |10-day move| limit for the wide condor
FWD_WIDE_MIN_CREDIT_PCT = 45.0    # 45% of 400 = 180 points
FWD_NARROW_MOVE_PCT     = 2.0     # |10-day move| limit for the normal (300-pt) condor (was 1.5 until 11-Oct-2026)
FWD_MIN_CREDIT_PCT      = 40.0    # floor: below 40% of 400 = 160 points -> no trade at all
FWD_WIDE_TP_FRACTION    = 0.60    # 60% target for the wide condor
# Put credit spread in the months the condor rule skips (adopted 27-Oct-2026, user's decision; README section 1b):
#   condor rule says SKIP -> sell the ~FWD_PCS_DELTA put, buy the put FWD_PCS_WIDTHS points lower,
#   UNLESS the 10-day move is > +FWD_PCS_RISE_PCT% and the last 5 days added <= +FWD_PCS_MIN_5D_PCT% (rally has stalled) -> no trade.
#   Target FWD_PCS_TP_FRACTION of the spread's own credit, stop SL_FRACTION, same 15:16 check and 18-DTE time exit, 1 lot.
FWD_PCS_DELTA           = 0.20    # sold put delta
FWD_PCS_WIDTHS          = [200]   # traded hedge width. 300 makes more (2021-26 Rs 16.3k vs 12.1k) but risks ~Rs 16.8k a lot vs
                                  # ~Rs 11.0k (beyond the 2-3% rule) -> priced as a shadow line (FWD_PCS_ALT_WIDTHS);
                                  # review after 6-12 months with the condor width (e.g. [300]).
FWD_PCS_ALT_WIDTHS      = [300]   # priced and logged only
FWD_PCS_RISE_PCT        = 2.5     # 5-day check applies after a 10-day rise above this
FWD_PCS_MIN_5D_PCT      = 1.0     # ... and then needs the last 5 days > +1%
FWD_PCS_TP_FRACTION     = 0.50
def _frac(v):                # IC_TP=40 or 0.4 -> 0.40
    v = float(v)
    return v / 100 if v > 1 else v
TP_FRACTION  = _frac(os.environ.get("IC_TP", 0.50))   # exit when P&L >= 50% of initial credit (IC_TP / --tp per run)
SL_FRACTION  = 1.00         # exit when loss >= 100% of initial credit
EXIT_DTE     = int(os.environ.get("IC_EXIT_DTE", 18))   # exit on last trading day on/before (expiry - 18 calendar days)
                           # (IC_EXIT_DTE / --exit-dte per run)
REF_EXIT_DTE = _IDX["ref_exit_dte"]   # exit DTE used in the StockMock reference run (NIFTY 15; reconciliation labels)
HEDGE_WIDTH  = int(os.environ.get("IC_HEDGE_WIDTH", _IDX["hedge_width"]))  # bought strike = sold strike +/- this many
                           # points (NIFTY 300, chosen 27-Sep-2026; StockMock reference = 200; each width needs its own download)
HEDGE_WIDTH_CE = int(os.environ.get("IC_HEDGE_WIDTH_CE", HEDGE_WIDTH))   # per-side override (call hedge)
HEDGE_WIDTH_PE = int(os.environ.get("IC_HEDGE_WIDTH_PE", HEDGE_WIDTH))   # per-side override (put hedge)
REF_HEDGE_WIDTH = _IDX["ref_hedge_width"]   # hedge width used in the StockMock reference run (NIFTY 200; reconciliation labels)
# Entry filter (adopted 28-Sep-2026): skip the month if NIFTY moved more than this % (up or down) over the
# last TREND_LOOKBACK_DAYS trading days, measured at the close before entry. None = no filter.
# Needs data/nifty_daily.csv (python download.py --index).
SKIP_IF_10D_MOVE_PCT = (None if os.environ.get("IC_TREND_FILTER", "").lower() == "off"
                        else float(os.environ.get("IC_TREND_FILTER") or 2.5))   # IC_TREND_FILTER=off to disable
TREND_LOOKBACK_DAYS  = 10
# Optional gap-up exit (tested 2-Oct-2026, OFF by default): on a day NIFTY opens at least this % above the
# previous close (data/nifty_daily.csv), exit all legs at that day's CHECK_TIME (15:16). Not on the entry day.
# None = off. Per run: IC_GAP_UP_EXIT=1.0 (or off).
GAP_UP_EXIT_PCT = (None if os.environ.get("IC_GAP_UP_EXIT", "off").lower() == "off"
                   else float(os.environ["IC_GAP_UP_EXIT"]))
# Optional call-side breach exit (tested 3-Oct-2026, OFF by default): exit all legs at CHECK_TIME on a day NIFTY
# closes at or above sold CE strike + this many points (300 = the hedge strike with 300-pt hedges; 0 = sold strike).
# Uses the daily close in data/nifty_daily.csv (live: NIFTY at 15:16). "hedge" = the bought CE strike.
_ce = os.environ.get("IC_CE_BREACH_EXIT", "off").lower()
CE_BREACH_EXIT_PTS = None if _ce == "off" else ("hedge" if _ce == "hedge" else float(_ce))

# ---- entry-day experiments ----
# Shift every entry this many calendar days from StockMock's entry (Monday): 2 = Wednesday, -3 = previous Friday.
# A non-trading day moves to the next trading day (positive shift) or the previous one (negative shift). Shifted entries have no StockMock prices, so pair it
# with a delta-based strike set (select_strikes.py) chosen on the shifted day. IC_ENTRY_SHIFT=2 per run.
ENTRY_SHIFT_DAYS = int(os.environ.get("IC_ENTRY_SHIFT", 0))

# ---- delta-based strike sets (python select_strikes.py; IC_STRIKE_SET=<name> to use one) ----
STRIKE_SET     = os.environ.get("IC_STRIKE_SET", "")   # "" = StockMock's sold strikes
STRIKE_SETS_DIR = DATA_DIR / STRATEGY / "strike_sets" / ("" if INDEX == "NIFTY" else INDEX.lower())   # strikes_<name>.csv

# ---- price rules specific to the condor backtest ----
USE_REFERENCE_ENTRY_IF_MISSING = True   # entry leg with no Breeze price -> StockMock's price (flagged REF)
# Fallback strikes (strategies/iron_condor/fallback.py): a side with no usable entry price moves its whole spread to the nearest
# priced strikes (closer first), else widens the hedge. IC_FALLBACK=off to disable.
FALLBACK_STRIKES       = os.environ.get("IC_FALLBACK", "").lower() != "off"
FALLBACK_SHIFTS        = _IDX["fallback_shifts"]        # points; negative = closer to the money (NIFTY -50/+50/-100/+100)
FALLBACK_HEDGE_EXTRA   = _IDX["fallback_hedge_extra"]   # widen the hedge by this much (NIFTY 350/400 for 300-pt hedges)

# ---- reconciliation vs StockMock ----
RECON_PNL_TOL_PTS = 3.0     # P&L difference (points) still counted as a match
BOUNDARY_BAND     = 0.03    # StockMock P&L within +/-3% of credit of TP/SL -> "boundary" trade
