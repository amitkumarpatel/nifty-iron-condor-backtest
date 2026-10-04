"""All settings in one place. Secrets live in .env (see .env.example), never here."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv missing -> plain environment variables still work
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(ROOT / ".env")

# ---- folders & files (IC_DATA_DIR / IC_OUTPUT_DIR override them; used by the smoke test) ----
DATA_DIR     = Path(os.environ.get("IC_DATA_DIR", ROOT / "data"))
OUTPUT_DIR   = Path(os.environ.get("IC_OUTPUT_DIR", ROOT / "output"))
REF_DIR      = ROOT / "data" / "reference"
TRADES_CSV   = REF_DIR / "ic_reference_trades.csv"
LEGS_CSV     = REF_DIR / "ic_reference_legs.csv"
CACHE_DIR    = DATA_DIR / "cache"                    # 1-minute candles, one CSV per contract per day
CALENDAR_CSV = DATA_DIR / "nifty_trading_days.csv"   # NSE trading days (from NIFTY daily candles)
REPORT_XLSX  = OUTPUT_DIR / "IC_backtest_report.xlsx"
INDEX_DAILY  = {"NIFTY": DATA_DIR / "nifty_daily.csv",       # daily OHLC for trend/VIX filters
                "INDVIX": DATA_DIR / "india_vix_daily.csv"}   # (python download.py --index)
PROBE_DIR    = OUTPUT_DIR / "probe"

# ---- strategy rules ----
ENTRY_TIME   = os.environ.get("IC_ENTRY_TIME", "11:16")   # close of the 1-minute candle labelled 11:16
ENTRY_DTE    = 43           # forward test: enter this many calendar days before expiry = the Monday six weeks
EXPIRY_WEEKDAY = "Tue"      # before a Tuesday monthly expiry (NIFTY expiries moved Thu -> Tue from Sep-2025; with
                            # Thursday expiries the same Monday was 45 DTE). If NSE changes the expiry day again,
                            # update both. The backtest takes its entry dates from the reference trades, not from here.
CHECK_TIME   = "15:16"      # one combined-position check per day
TP_FRACTION  = 0.50         # exit when P&L >= 50% of initial credit
SL_FRACTION  = 1.00         # exit when loss >= 100% of initial credit
EXIT_DTE     = 18           # exit on last trading day on/before (expiry - 18 calendar days)
REF_EXIT_DTE = 15           # exit DTE used in the StockMock reference run (for reconciliation labels)
HEDGE_WIDTH  = int(os.environ.get("IC_HEDGE_WIDTH", 300))  # bought strike = sold strike +/- this many points
                           # (chosen 27-Sep-2026; StockMock reference = 200; each width needs its own download)
HEDGE_WIDTH_CE = int(os.environ.get("IC_HEDGE_WIDTH_CE", HEDGE_WIDTH))   # per-side override (call hedge)
HEDGE_WIDTH_PE = int(os.environ.get("IC_HEDGE_WIDTH_PE", HEDGE_WIDTH))   # per-side override (put hedge)
REF_HEDGE_WIDTH = 200       # hedge width used in the StockMock reference run (for reconciliation labels)
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
STRIKE_SETS_DIR = DATA_DIR / "strike_sets"             # strikes_<name>.csv: trade_id, opt_type, strike
SPOT_KEY       = "NIFTY_SPOT"                          # cache folder for NIFTY 1-minute spot candles
STRIKE_STEP    = 50                                    # NIFTY option strike spacing
RISK_FREE_RATE = 0.065                                 # Black-Scholes inputs for delta at entry
DIV_YIELD      = 0.0

# ---- NIFTY lot size by expiry (1 lot per trade) ----
# (last expiry date, lot size) - first row whose date >= the trade's expiry applies.
# 50 -> 25 for contracts from 26-Apr-2024 (NSE); 25 -> 75 for contracts introduced from 20-Nov-2024,
# existing Dec-2024 and Jan-2025 monthlies kept 25 until expiry; 75 -> 65 from the Jan-2026 expiry.
LOT_SIZES = [("2024-05-30", 50), ("2025-01-30", 25), ("2025-12-30", 75), ("2099-12-31", 65)]

# ---- data handling ----
STALE_WARN_MIN = 15                     # fallback price older than this is flagged STALE
USE_REFERENCE_ENTRY_IF_MISSING = True   # entry leg with no Breeze price -> StockMock's price (flagged REF)
MAX_AFTER_MIN_AT_ENTRY = 15             # entry price from a trade later than this after ENTRY_TIME is rejected
# Fallback strikes (ic/fallback.py): a side with no usable entry price moves its whole spread to the nearest
# priced strikes (closer first), else widens the hedge. IC_FALLBACK=off to disable.
FALLBACK_STRIKES       = os.environ.get("IC_FALLBACK", "").lower() != "off"
FALLBACK_SHIFTS        = [-50, 50, -100, 100]   # points; negative = closer to the money
FALLBACK_HEDGE_EXTRA   = [50, 100]   # widen the hedge by this much (350/400 for 300-pt hedges)
EXTRA_HOLIDAYS = ["2026-09-14"]         # confirmed holidays, always removed from the calendar
# Diwali Muhurat sessions (special ~1-hour session, no 15:16 candle). Treated as non-trading days:
# no daily check and never a time-exit day. Add each new year's date once NSE announces it.
MUHURAT_DAYS = ["2020-11-14", "2021-11-04", "2022-10-24", "2023-11-12", "2024-11-01", "2025-10-21"]

# ---- Breeze API limits ----
PAUSE_SEC        = float(os.environ.get("IC_PAUSE_SEC", 0.65))   # stays under 100 calls/min
DAILY_CALL_LIMIT = 4800                                         # Breeze allows 5000/day

# ---- costs (approximate; check your broker's contract note) ----
COSTS = dict(
    brokerage_per_order  = 20.0,     # Rs per executed order (8 orders per condor)
    stt_sell_pct         = 0.10,     # % of premium on sell-side turnover
    exch_txn_pct         = 0.03503,  # % of premium turnover (NSE options)
    sebi_per_crore       = 10.0,     # Rs per crore of turnover
    stamp_buy_pct        = 0.003,    # % of buy-side premium
    gst_pct              = 18.0,     # on brokerage + exchange + SEBI charges
    slippage_pts_per_leg = 0.0,      # adverse points per leg per side (try 0.5 or 1.0)
)

# ---- reconciliation vs StockMock ----
RECON_PNL_TOL_PTS = 3.0     # P&L difference (points) still counted as a match
BOUNDARY_BAND     = 0.03    # StockMock P&L within +/-3% of credit of TP/SL -> "boundary" trade
