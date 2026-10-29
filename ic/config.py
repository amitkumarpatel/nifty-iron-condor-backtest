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

# ---- index (IC_INDEX=BANKNIFTY or --symbol banknifty on any script; default NIFTY) ----
# Everything that differs between indices lives in this table. The rules below (entry, exits, filter) are
# shared. NIFTY's values are the ones the project has always used; with IC_INDEX unset nothing changes.
#   breeze_code     ICICI Breeze stock code of the index (options and 1-minute spot)
#   nse_name        the index's name in NSE's daily index file (official close; ic/nse_index.py)
#   strike_step     option strike spacing
#   hedge_width     default distance of the bought legs (IC_HEDGE_WIDTH / --hedge overrides it)
#   ref_hedge_width, ref_exit_dte  hedge width and exit DTE of the StockMock reference run (reconciliation labels)
#   fallback_*      ic/fallback.py: spread shifts (negative = closer to the money) and extra hedge width
#   start_vol_factor  make_trades.py only: index volatility as a multiple of India VIX (rough start strikes)
#   expiry_weekdays (last month that uses it, weekday of the monthly expiry: Mon=0 .. Thu=3) - make_trades.py only
#   lot_sizes       (last expiry date, lot size) - first row whose date >= the trade's expiry applies
INDEX = os.environ.get("IC_INDEX", "NIFTY").upper()
INDEXES = {
    "NIFTY": dict(
        breeze_code="NIFTY", nse_name="nifty 50", strike_step=50, hedge_width=300, ref_hedge_width=200, ref_exit_dte=15,
        fallback_shifts=[-50, 50, -100, 100], fallback_hedge_extra=[50, 100], start_vol_factor=1.0,
        expiry_weekdays=[("2025-08", 3), ("2099-12", 1)],          # Thursday, Tuesday from Sep-2025
        # 50 -> 25 for contracts from 26-Apr-2024 (NSE); 25 -> 75 for contracts introduced from 20-Nov-2024,
        # existing Dec-2024 and Jan-2025 monthlies kept 25 until expiry; 75 -> 65 from the Jan-2026 expiry.
        # 75 for expiries up to Jun-2021: NSE circular FAOP47854 (31-Mar-2021) cut 75 -> 50 only from the Jul-2021
        # expiry contracts (fixed 29-Oct-2026; StockMock's quantity of 50 for Feb-Jun 2021 expiries was too small).
        lot_sizes=[("2021-06-24", 75),("2024-05-30", 50), ("2025-01-30", 25), ("2025-12-30", 75), ("2099-12-31", 65)],
    ),
    # BANKNIFTY added 11-Oct-2026. hedge_width 500 and the 18-DTE exit = the user's StockMock run ("Banknifty IC
    # backtesting_StockMock.xlsx", 67 trades). expiry_weekdays reproduce all 67 expiries of that report. lot_sizes
    # match its quantities except the Jul-2023 and Aug-2023 expiries: StockMock used 25, NSE circular FAOP56233
    # (31-Mar-2023) made the lot 15 from the July-2023 expiry - the engine uses 15.
    # breeze_code CNXBAN confirmed by the probe of 11-Oct-2026 (64/64 checks returned data).
    "BANKNIFTY": dict(
        breeze_code="CNXBAN", nse_name="nifty bank", strike_step=100, hedge_width=500, ref_hedge_width=500, ref_exit_dte=18,
        fallback_shifts=[-100, 100, -200, 200], fallback_hedge_extra=[100, 200], start_vol_factor=1.25,
        # Thursday; Wednesday Mar-2024..Dec-2024; Thursday Jan..Aug-2025; Tuesday from Sep-2025
        expiry_weekdays=[("2024-02", 3), ("2024-12", 2), ("2025-08", 3), ("2099-12", 1)],
        lot_sizes=[("2020-06-25", 20), ("2023-06-29", 25), ("2025-01-30", 15), ("2025-06-26", 30),
                   ("2025-12-30", 35), ("2099-12-31", 30)],
    ),
}
if INDEX not in INDEXES:
    raise SystemExit(f"Unknown index '{INDEX}' (IC_INDEX / --symbol). Known: {', '.join(INDEXES)}")
_IDX = INDEXES[INDEX]
BREEZE_CODE = _IDX["breeze_code"]
# File names: NIFTY keeps the original names; another index gets its name in front (banknifty_..., BANKNIFTY_...).
FILE_PREFIX = "" if INDEX == "NIFTY" else INDEX.lower() + "_"

# ---- folders & files (IC_DATA_DIR / IC_OUTPUT_DIR / IC_REF_DIR override them; used by the smoke test) ----
DATA_DIR     = Path(os.environ.get("IC_DATA_DIR", ROOT / "data"))
OUTPUT_DIR   = Path(os.environ.get("IC_OUTPUT_DIR", ROOT / "output"))
REF_DIR      = Path(os.environ.get("IC_REF_DIR", ROOT / "data" / "reference"))
# Trade set: "" = the StockMock reference trades; IC_TRADE_SET=<name> (or --trade-set) = a generated set
# (python make_trades.py) in ic_trades_<name>.csv / ic_legs_<name>.csv, e.g. years StockMock never ran.
TRADE_SET    = os.environ.get("IC_TRADE_SET", "")
TRADES_CSV   = REF_DIR / (FILE_PREFIX + (f"ic_trades_{TRADE_SET}.csv" if TRADE_SET else "ic_reference_trades.csv"))
LEGS_CSV     = REF_DIR / (FILE_PREFIX + (f"ic_legs_{TRADE_SET}.csv" if TRADE_SET else "ic_reference_legs.csv"))
CACHE_DIR    = DATA_DIR / "cache"                    # 1-minute candles, one CSV per contract per day
CALENDAR_CSV = DATA_DIR / "nifty_trading_days.csv"   # NSE trading days (from NIFTY daily candles; all indices)
REPORT_XLSX  = OUTPUT_DIR / (FILE_PREFIX.upper() + "IC_backtest_report.xlsx")
INDEX_DAILY  = {"NIFTY": DATA_DIR / "nifty_daily.csv",       # daily OHLC for trend/VIX filters
                "INDVIX": DATA_DIR / "india_vix_daily.csv",   # (python fetch_index_nse.py / download.py --index)
                "BANKNIFTY": DATA_DIR / "banknifty_daily.csv"}
INDEX_DAILY_CSV = INDEX_DAILY[INDEX]                 # the traded index: trend filter, gap-up and breach exits
DAILY_BREEZE_CODES = {"NIFTY": "NIFTY", "INDVIX": "INDVIX", "BANKNIFTY": INDEXES["BANKNIFTY"]["breeze_code"]}
PROBE_DIR    = OUTPUT_DIR / ("probe" if INDEX == "NIFTY" else f"probe_{INDEX.lower()}")

# ---- strategy rules ----
ENTRY_TIME   = os.environ.get("IC_ENTRY_TIME", "11:16")   # close of the 1-minute candle labelled 11:16
ENTRY_DTE    = 43           # forward test: enter this many calendar days before expiry = the Monday six weeks
EXPIRY_WEEKDAY = "Tue"      # before a Tuesday monthly expiry (NIFTY expiries moved Thu -> Tue from Sep-2025; with
                            # Thursday expiries the same Monday was 45 DTE). If NSE changes the expiry day again,
                            # update both. The backtest takes its entry dates from the reference trades, not from here.
CHECK_TIME   = "15:16"      # one combined-position check per day

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
STRIKE_SETS_DIR = DATA_DIR / "strike_sets" / ("" if INDEX == "NIFTY" else INDEX.lower())   # strikes_<name>.csv
SPOT_KEY       = f"{INDEX}_SPOT"                       # cache folder for the index's 1-minute spot candles
STRIKE_STEP    = _IDX["strike_step"]                   # option strike spacing (NIFTY 50)
RISK_FREE_RATE = 0.065                                 # Black-Scholes inputs for delta at entry
DIV_YIELD      = 0.0

# ---- lot size by expiry (1 lot per trade): the index's table in INDEXES above ----
LOT_SIZES = _IDX["lot_sizes"]
EXPIRY_WEEKDAYS  = _IDX["expiry_weekdays"]      # make_trades.py
START_VOL_FACTOR = _IDX["start_vol_factor"]     # make_trades.py

# ---- data handling ----
STALE_WARN_MIN = 15                     # fallback price older than this is flagged STALE
USE_REFERENCE_ENTRY_IF_MISSING = True   # entry leg with no Breeze price -> StockMock's price (flagged REF)
MAX_AFTER_MIN_AT_ENTRY = 15             # entry price from a trade later than this after ENTRY_TIME is rejected
# Fallback strikes (ic/fallback.py): a side with no usable entry price moves its whole spread to the nearest
# priced strikes (closer first), else widens the hedge. IC_FALLBACK=off to disable.
FALLBACK_STRIKES       = os.environ.get("IC_FALLBACK", "").lower() != "off"
FALLBACK_SHIFTS        = _IDX["fallback_shifts"]        # points; negative = closer to the money (NIFTY -50/+50/-100/+100)
FALLBACK_HEDGE_EXTRA   = _IDX["fallback_hedge_extra"]   # widen the hedge by this much (NIFTY 350/400 for 300-pt hedges)
EXTRA_HOLIDAYS = ["2026-09-14"]         # confirmed holidays, always removed from the calendar
# Diwali Muhurat sessions (special ~1-hour session, no 15:16 candle). Treated as non-trading days:
# no daily check and never a time-exit day. Add each new year's date once NSE announces it.
MUHURAT_DAYS = ["2020-11-14", "2021-11-04", "2022-10-24", "2023-11-12", "2024-11-01", "2025-10-21", "2026-11-08"]
# NSE trading holidays (F&O segment) for the forward-test calendar (entry and time-exit dates). Written by
# `python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py holidays --write` from NSE's website - run it
# each January (and after any special holiday announcement); do not edit the block by hand. The backtest does
# not use it: its calendar comes from the days NIFTY actually traded.
# NSE_HOLIDAYS_START
# fetched from NSE on 2026-10-04 (FO segment, years [2026])
NSE_HOLIDAYS = [
    "2026-01-15",  # Thu Municipal Corporation Election - Maharashtra
    "2026-01-26",  # Mon Republic Day
    "2026-02-15",  # Sun Mahashivratri
    "2026-03-03",  # Tue Holi
    "2026-03-21",  # Sat Id-Ul-Fitr (Ramadan Eid)
    "2026-03-26",  # Thu Shri Ram Navami
    "2026-03-31",  # Tue Shri Mahavir Jayanti
    "2026-04-03",  # Fri Good Friday
    "2026-04-14",  # Tue Dr. Baba Saheb Ambedkar Jayanti
    "2026-05-01",  # Fri Maharashtra Day
    "2026-05-28",  # Thu Bakri Id
    "2026-06-26",  # Fri Muharram
    "2026-08-15",  # Sat Independence Day
    "2026-09-14",  # Mon Ganesh Chaturthi
    "2026-10-02",  # Fri Mahatma Gandhi Jayanti
    "2026-10-20",  # Tue Dussehra
    "2026-11-08",  # Sun Diwali Laxmi Pujan*
    "2026-11-10",  # Tue Diwali-Balipratipada
    "2026-11-24",  # Tue Prakash Gurpurb Sri Guru Nanak Dev
    "2026-12-25",  # Fri Christmas
]
# NSE_HOLIDAYS_END

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
