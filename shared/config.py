"""Settings shared by every strategy: index table, data folders, calendar and holidays, lot sizes, price rules,
Breeze limits and costs. Strategy rules live in strategies/<name>/config.py, which imports everything from here.
Secrets live in .env (see .env.example), never here."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv missing -> plain environment variables still work
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent          # repository root
if load_dotenv:
    load_dotenv(ROOT / ".env")

# ---- index (IC_INDEX=BANKNIFTY or --symbol banknifty on any script; default NIFTY) ----
# Everything that differs between indices lives in this table. The rules below (entry, exits, filter) are
# shared. NIFTY's values are the ones the project has always used; with IC_INDEX unset nothing changes.
#   breeze_code     ICICI Breeze stock code of the index (options and 1-minute spot)
#   nse_name        the index's name in NSE's daily index file (official close; shared/nse_index.py)
#   strike_step     option strike spacing
#   hedge_width     default distance of the bought legs (IC_HEDGE_WIDTH / --hedge overrides it)
#   ref_hedge_width, ref_exit_dte  hedge width and exit DTE of the StockMock reference run (reconciliation labels)
#   fallback_*      strategies/iron_condor/fallback.py: spread shifts (negative = closer to the money) and extra hedge width
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

# ---- folders shared by all strategies (IC_DATA_DIR / IC_OUTPUT_DIR override them; used by the smoke test) ----
# Each strategy keeps its own reference files under data/<strategy>/ and writes reports to output/<strategy>/.
DATA_DIR     = Path(os.environ.get("IC_DATA_DIR", ROOT / "data"))
OUTPUT_ROOT  = Path(os.environ.get("IC_OUTPUT_DIR", ROOT / "output"))
CACHE_DIR    = DATA_DIR / "cache"                    # 1-minute candles, one CSV per contract per day (all strategies)
CALENDAR_CSV = DATA_DIR / "nifty_trading_days.csv"   # NSE trading days (from NIFTY daily candles; all indices)
INDEX_DAILY  = {"NIFTY": DATA_DIR / "nifty_daily.csv",       # daily OHLC for trend/VIX filters
                "INDVIX": DATA_DIR / "india_vix_daily.csv",   # (shared/scripts/fetch_index_nse.py / download --index)
                "BANKNIFTY": DATA_DIR / "banknifty_daily.csv"}
INDEX_DAILY_CSV = INDEX_DAILY[INDEX]                 # the traded index: trend filter, gap-up and breach exits
DAILY_BREEZE_CODES = {"NIFTY": "NIFTY", "INDVIX": "INDVIX", "BANKNIFTY": INDEXES["BANKNIFTY"]["breeze_code"]}

# ---- timing shared by the strategies (entry Monday 11:16 at 43 DTE, one check a day at 15:16) ----
ENTRY_TIME   = os.environ.get("IC_ENTRY_TIME", "11:16")   # close of the 1-minute candle labelled 11:16
ENTRY_DTE    = 43           # forward test: enter this many calendar days before expiry = the Monday six weeks
EXPIRY_WEEKDAY = "Tue"      # before a Tuesday monthly expiry (NIFTY expiries moved Thu -> Tue from Sep-2025; with
                            # Thursday expiries the same Monday was 45 DTE). If NSE changes the expiry day again,
                            # update both. The backtests take their entry dates from their trade lists, not from here.
CHECK_TIME   = "15:16"      # one combined-position check per day

# ---- spot and Black-Scholes inputs (delta-based strike selection) ----
SPOT_KEY       = f"{INDEX}_SPOT"                       # cache folder for the index's 1-minute spot candles
STRIKE_STEP    = _IDX["strike_step"]                   # option strike spacing (NIFTY 50)
RISK_FREE_RATE = 0.065
DIV_YIELD      = 0.0

# ---- lot size by expiry (1 lot per trade): the index's table in INDEXES above ----
LOT_SIZES = _IDX["lot_sizes"]
EXPIRY_WEEKDAYS  = _IDX["expiry_weekdays"]      # make_trades.py
START_VOL_FACTOR = _IDX["start_vol_factor"]     # make_trades.py

# ---- data handling ----
STALE_WARN_MIN = 15                     # fallback price older than this is flagged STALE
MAX_AFTER_MIN_AT_ENTRY = 15             # entry price from a trade later than this after ENTRY_TIME is rejected
EXTRA_HOLIDAYS = ["2026-09-14"]         # confirmed holidays, always removed from the calendar
# Diwali Muhurat sessions (special ~1-hour session, no 15:16 candle). Treated as non-trading days:
# no daily check and never a time-exit day. Add each new year's date once NSE announces it.
MUHURAT_DAYS = ["2020-11-14", "2021-11-04", "2022-10-24", "2023-11-12", "2024-11-01", "2025-10-21", "2026-11-08"]
# NSE trading holidays (F&O segment) for the forward-test calendar (entry and time-exit dates). Written by
# `python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py holidays --write` from NSE's website
# (it rewrites the block below in this file, shared/config.py) - run it
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
    brokerage_per_order  = 20.0,     # Rs per executed order (8 orders per condor, 4 per spread)
    stt_sell_pct         = 0.10,     # % of premium on sell-side turnover
    exch_txn_pct         = 0.03503,  # % of premium turnover (NSE options)
    sebi_per_crore       = 10.0,     # Rs per crore of turnover
    stamp_buy_pct        = 0.003,    # % of buy-side premium
    gst_pct              = 18.0,     # on brokerage + exchange + SEBI charges
    slippage_pts_per_leg = 0.0,      # adverse points per leg per side (try 0.5 or 1.0)
)

