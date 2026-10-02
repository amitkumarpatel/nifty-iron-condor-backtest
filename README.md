# NIFTY Monthly Iron Condor – Backtest Automation

Replays a StockMock-backtested NIFTY monthly iron condor on real 1-minute option prices from the
**ICICI Direct Breeze API**, applies the exit rules exactly as specified, and produces an Excel
report that reconciles every trade against StockMock.

The goal is to verify the StockMock results independently, measure the impact of real costs and
slippage, and have a rule-based engine that can later be extended towards live trading.

---

## Quick start

First time (details in sections 3–5):

```bash
cd nifty-iron-condor-backtest
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env                 # add BREEZE_API_KEY and BREEZE_API_SECRET
python tests/smoke_test.py           # offline check that everything works (no API needed)

python login_url.py                  # log in, put today's apisession value in .env (BREEZE_SESSION)
python download.py --index           # NIFTY + India VIX daily prices (a few API calls)
python download.py                   # 1-minute option candles (~3,500 API calls, restart-safe)
python backtest.py                   # offline -> output/IC_backtest_report.xlsx
```

Every later session:

```bash
cd nifty-iron-condor-backtest
source .venv/bin/activate
python backtest.py                   # offline, uses the cached data
```

You only need a new session token (`python login_url.py`) for commands that call the Breeze API:
`download.py`, `probe.py` and `select_strikes.py`. `backtest.py` and the smoke test never use it.

---

## 1. Strategy rules

| Item | Rule |
|---|---|
| Underlying | NIFTY, next-month (monthly) expiry |
| Entry filter | **Skip the month** if NIFTY moved more than **2.5%** (up or down) over the last **10 trading days**, measured at the close before entry (`SKIP_IF_10D_MOVE_PCT`, `TREND_LOOKBACK_DAYS`). Adopted 28-Sep-2026 – see §7 |
| Entry | 42–45 DTE, **11:16** (close of the 1-minute candle labelled 11:16) |
| Legs | Sell ~30-delta CE and PE (strikes from the StockMock report); buy CE and PE **300 points** further out (`HEDGE_WIDTH`; StockMock used 200). Changed from 200 on 27-Sep-2026 – see §7 |
| Check | Combined position checked **once a day at 15:16** – no intraday monitoring |
| Target | P&L ≥ **50%** of initial credit → exit all 4 legs |
| Stop-loss | Loss ≥ **100%** of initial credit → exit all 4 legs |
| Time exit | Last trading day on/before **expiry − 18 calendar days** (holiday/weekend/Muhurat session → previous trading day). Changed from 15 DTE on 27-Sep-2026 – see §7 |
| Optional: gap-up exit | **Off by default.** If on (`GAP_UP_EXIT_PCT` / `IC_GAP_UP_EXIT=1.0`): on a day NIFTY opens ≥ 1% above the previous close, exit all 4 legs at that day's 15:16 check (never on the entry day). Tested 2-Oct-2026 – see §7 |
| Sizing | **1 lot** at each expiry's NIFTY lot size (50 → 25 → 75 → 65, `LOT_SIZES`) |
| Not allowed | Adjustments, re-entry, quantity change, other entry filters |

Order of checks each day: stop-loss → target → time exit.

---

## 2. Project structure

```
nifty-iron-condor-backtest/
├── README.md
├── CLAUDE.md               # project context for Claude Code
├── requirements.txt
├── .env.example            # template for your Breeze credentials (copy to .env)
├── .gitignore
├── login_url.py            # prints today's Breeze login URL
├── probe.py                # quick data-availability / price-match check
├── download.py             # downloads 1-minute candles (and --index: NIFTY/VIX daily) into data/
├── select_strikes.py       # optional: pick sold strikes by delta (experiments)
├── backtest.py             # runs the engine and writes the Excel report
├── export_prices.py        # daily option prices of every trade leg (for analysis)
├── ic/                     # the code
│   ├── config.py           # ALL settings: rules, filter, lot sizes, costs, paths, limits
│   ├── breeze_client.py    # login (reads .env)
│   ├── common.py           # calendar, contracts, lot sizes, trend move, cache paths
│   ├── downloader.py       # option candles, NIFTY/VIX daily, fallback-strike candles
│   ├── engine.py           # trade replay, exits, report
│   ├── export.py           # daily leg-price export
│   ├── fallback.py         # nearest priced strikes when a leg has no price at entry
│   ├── strikes.py          # delta-based strike selection
│   └── probe.py
├── data/
│   ├── reference/          # committed: StockMock exports + clean trade/leg lists
│   │   ├── stockmock_export.xlsx
│   │   ├── ic_reference_trades.csv
│   │   └── ic_reference_legs.csv
│   ├── strike_sets/        # strikes chosen by select_strikes.py (experiments)
│   ├── cache/              # NOT committed: downloaded candles (one CSV per contract per day)
│   ├── nifty_daily.csv     # NOT committed: NIFTY daily OHLC (trend filter) – download.py --index
│   ├── india_vix_daily.csv # NOT committed: India VIX daily OHLC – download.py --index
│   └── nifty_trading_days.csv   # NOT committed: NSE calendar built by download.py
├── output/                 # NOT committed: reports, probe results, error logs
├── logs/                   # NOT committed: Breeze SDK logs
├── docs/
│   └── stockmock_validation.xlsx   # validation of the StockMock report
└── tests/
    ├── smoke_test.py       # offline end-to-end test with a fake Breeze client
    └── fake_breeze/
```

---

## 3. Setup (one time)

### 3.1 Prerequisites
- Python 3.9 or newer (`python3 --version`)
- An ICICI Direct trading account with a Breeze API app (free)

### 3.2 Get the code and create a virtual environment

On macOS with Homebrew Python, `pip install` outside a virtual environment fails with
`externally-managed-environment` – always use the venv.

```bash
cd nifty-iron-condor-backtest
python3 -m venv .venv
source .venv/bin/activate          # prompt now starts with (.venv)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Every new Terminal window: `cd` into the project and run `source .venv/bin/activate` again.

### 3.3 Create the Breeze API key
1. Go to https://api.icicidirect.com/apiuser/home and log in with your ICICI Direct credentials.
2. Register an app: any name, redirect URL `http://127.0.0.1`, and your public IP as the static IP
   (only order placement is IP-restricted; this project only reads historical data).
3. Open **View Apps** and note the **API key** and **Secret key**.

### 3.4 Create the `.env` file

```bash
cp .env.example .env
```

Edit `.env`:

```
BREEZE_API_KEY=your_api_key
BREEZE_API_SECRET=your_secret_key
BREEZE_SESSION=                 # filled daily, see section 4
```

`.env` is in `.gitignore` – never commit it and never paste its contents anywhere.

---

## 4. Daily login (session token)

Breeze requires a new session token every day (valid until midnight / 24 hours).

```bash
python login_url.py
```

1. Open the printed URL, log in (user ID, password, OTP/TOTP).
2. The browser is redirected to something like `http://127.0.0.1/?apisession=12345678`
   ("can't connect" is normal).
3. Copy the number after `apisession=` into `BREEZE_SESSION` in `.env`.

If `BREEZE_SESSION` is empty, the scripts ask for it when they start.

---

## 5. Commands

Run every command from the project folder with the virtual environment active
(`source .venv/bin/activate`).

### 5.0 Command reference

| Command | What it does | Breeze API? | Output |
|---|---|---|---|
| `python tests/smoke_test.py` | Offline end-to-end test with a fake Breeze client (run after any code change) | No | console, temp folder |
| `python login_url.py` | Prints today's Breeze login URL | No | console |
| `python probe.py [--trades 9 67] [--all]` | Checks that Breeze has the data and prices match StockMock | Yes (~64 calls) | `output/probe/` |
| `python download.py --index` | NIFTY and India VIX daily prices (needed by the trend filter) | Yes (a few calls) | `data/nifty_daily.csv`, `data/india_vix_daily.csv` |
| `python download.py [--trades ...]` | 1-minute candles for every leg, plus fallback strikes; restart-safe | Yes (~3,500 calls first time) | `data/cache/` |
| `python backtest.py` | Replays all trades with the current rules | No | `output/IC_backtest_report.xlsx` |
| `python backtest.py --trades 1 9 23 --out output/x.xlsx` | Selected trades / separate report file | No | the `--out` file |
| `python export_prices.py [--trades ...] [--out file]` | Daily price of every leg of every trade, entry to exit (11:16 entry, 15:16 checks, day OHLC), incl. filter-skipped months | No | `output/IC_leg_prices.xlsx` |
| `python select_strikes.py --ce-delta 0.25 --name ce25` | Experiment: choose sold strikes by delta | Yes | `data/strike_sets/` |

### 5.0a Settings you can change per run (environment variables)

Put them in front of a command, e.g. `IC_TREND_FILTER=off python backtest.py --out output/nofilter.xlsx`.
Permanent changes go in `ic/config.py`.

| Variable | Default | Effect |
|---|---|---|
| `IC_TREND_FILTER` | `2.5` | 10-day move limit in %; `off` disables the entry filter |
| `IC_HEDGE_WIDTH` | `300` | points between sold and bought strikes (200, 300 and 400 are downloaded) |
| `IC_HEDGE_WIDTH_CE`, `IC_HEDGE_WIDTH_PE` | = `IC_HEDGE_WIDTH` | different call / put hedge widths (e.g. CE 300, PE 400) |
| `IC_FALLBACK` | on | `off` disables the fallback strikes |
| `IC_GAP_UP_EXIT` | `off` | e.g. `1.0`: exit at 15:16 on a day NIFTY opens ≥ 1% above the previous close |
| `IC_STRIKE_SET` | – | use strikes from `data/strike_sets/strikes_<name>.csv` (select_strikes.py) |
| `IC_ENTRY_SHIFT` | `0` | experiment: shift the entry N calendar days from StockMock's Monday (2 = Wednesday, −3 = previous Friday; holidays move forward / back). Use with a strike set chosen on that day |
| `IC_ENTRY_TIME` | `11:16` | entry time, e.g. `15:16` for the Friday roll test (exit old and enter new at the same check) |
| `IC_DATA_DIR`, `IC_OUTPUT_DIR` | `data/`, `output/` | alternative folders (used by the smoke test) |
| `IC_PAUSE_SEC` | `0.65` | pause between API calls (stays under 100 calls/min) |


### 5.1 Check that Breeze has the data (probe)
Fast check (~64 API calls) on a sample of 8 trades across 2021–2026: coverage, price match with
StockMock, and which candle label matches best.

```bash
python probe.py                                   # default sample
python probe.py --trades 9 67                     # specific trades
python probe.py --trades 67 --exit-override 67=2026-09-11   # test a different exit date
python probe.py --all                             # every trade (~536 calls)
```
Results: console summary + `output/probe/probe_results.csv` (raw responses in `output/probe/raw/`).

### 5.2 Download the data (first run)
```bash
python download.py
```
- Builds the NSE trading calendar from NIFTY daily candles.
- Downloads 1-minute candles for all 4 legs of all 67 trades, for every trading day from entry to
  the latest possible exit, plus the fallback strikes for legs with no price at entry
  (~3,500 API calls, 2 trading days per call, ~40 minutes).
- Run `python download.py --index` as well (section 5.3a) – the backtest needs NIFTY daily prices
  for the trend filter.
- Breeze allows 5,000 calls/day; the script stops at 4,800 to keep a margin.

### 5.3 Resume an interrupted download
Just run it again (with today's session token if the day changed):
```bash
python download.py
```
Already-downloaded contract-days are skipped. It also fetches the fallback strikes for trades with a
leg that has no usable entry price (entry day of the candidates first, then the chosen strikes).
Failed chunks are listed in
`output/download_errors.csv` and retried automatically on the next run.

### 5.3a NIFTY and India VIX daily prices (needed by the trend filter)
```bash
python download.py --index
```
A handful of API calls. Saves daily OHLC to `data/nifty_daily.csv` and `data/india_vix_daily.csv`
(`config.INDEX_DAILY`). The backtest needs `nifty_daily.csv` for the trend filter; re-run this
command to extend it before backtesting new months.

### 5.3b Delta-based strikes (e.g. a 25-delta call)
```bash
python select_strikes.py --ce-delta 0.25 --name ce25      # API: NIFTY spot + candidate strikes on entry days
IC_STRIKE_SET=ce25 python download.py                      # API: full candles for the new strikes
IC_STRIKE_SET=ce25 python backtest.py --out output/IC_backtest_ce25.xlsx
```
`select_strikes.py` computes each candidate's Black-Scholes delta at 11:16 (NIFTY spot at that minute,
implied volatility from the option's own price, `RISK_FREE_RATE`, `DIV_YIELD`) and saves the strike
closest to the target in `data/strike_sets/strikes_<name>.csv` (plus every candidate in
`output/strike_selection_<name>.csv`). `--pe-delta` works the same way for puts.
`--trend-shift --with-delta 0.20 [--against-delta 0.35]` picks strikes only for the months beyond the
trend-filter limit: the leg on the trend side (CE after a rise, PE after a fall) at `--with-delta`, the
other leg at `--against-delta` (unchanged if omitted). `--range`/`--closer` widen the strike search;
`--dry-run` only counts the API calls; `--append` updates only the given `--trades` in an existing strike set. Experiment only – the adopted rule still skips these months. Hedges follow the new
sold strikes (`HEDGE_WIDTH`). Trades with no price at entry keep StockMock's strike (listed at the end).

### 5.4 Run the full backtest
Works offline from the cache – no API calls, no session token needed.
```bash
python backtest.py
```
Writes `output/IC_backtest_report.xlsx` and prints the summary and reconciliation.

### 5.5 Backtest selected trades only
```bash
python backtest.py --trades 1 9 23 --out output/selected_trades.xlsx
```

### 5.6 Test a rule variation
Edit `ic/config.py`, then re-run with a separate output file so results don't overwrite each other:

| Change | Setting | Needs new download? |
|---|---|---|
| Target, e.g. 40% | `TP_FRACTION = 0.40` | No |
| Stop-loss, e.g. 150% | `SL_FRACTION = 1.50` | No |
| Entry/check time | `ENTRY_TIME`, `CHECK_TIME` | No (full days are cached) |
| Trend filter off / other threshold | `IC_TREND_FILTER=off` or `IC_TREND_FILTER=3` before the command (or `SKIP_IF_10D_MOVE_PCT`) | No – needs `data/nifty_daily.csv` (`python download.py --index`) |
| Exit earlier, e.g. 21 DTE | `EXIT_DTE = 21` | No |
| Old rule, 15 DTE (StockMock's rule) | `EXIT_DTE = 15` | No – existing trades are cached up to their StockMock exit (~15 DTE) |
| Fallback strikes off | `IC_FALLBACK=off` before the command | No |
| Gap-up exit on | `IC_GAP_UP_EXIT=1.0` before the command (or `GAP_UP_EXIT_PCT = 1.0`) | No – needs `data/nifty_daily.csv` |
| Hold longer, e.g. 7 DTE | `EXIT_DTE = 7` | **Yes** – run `python download.py` (fetches only the extra days) |
| Hedge width (default 300) | `HEDGE_WIDTH`, or `IC_HEDGE_WIDTH=200` before the command | 200 and 300 are already cached. Any other width: **yes** – `IC_HEDGE_WIDTH=<w> python download.py` (~1,300 calls), then `IC_HEDGE_WIDTH=<w> python backtest.py --out output/hedge<w>.xlsx`. Hedges other than 200 have no StockMock price, so the REF entry fallback does not apply to them |

```bash
python backtest.py --out output/tp40_sl150.xlsx
```
Remember to set `config.py` back afterwards (or commit variations on a separate git branch).

### 5.7 Cost and slippage sensitivity
In `ic/config.py`, adjust `COSTS` – e.g. `slippage_pts_per_leg = 0.5` (adverse 0.5 point per leg
per side). The Summary sheet shows gross and net-of-costs results side by side.

### 5.8 Add trades or a new StockMock export
Add rows to the two reference CSVs (same trade_id in both):

`data/reference/ic_reference_trades.csv`

| column | example | meaning |
|---|---|---|
| trade_id | 68 | unique number |
| entry_date | 2026-09-14 | entry day |
| entry_time | 11:16 | informational |
| expiry | 2026-10-27 | option expiry |
| sell_ce, buy_ce, sell_pe, buy_pe | 26000, 26200, 25000, 24800 | strikes |
| qty_stockmock | 65 | lot size in the StockMock report (info only – the engine uses `config.LOT_SIZES`) |
| ref_exit_date, ref_exit_reason, ref_pnl_pts, ref_pnl_rs | | StockMock results (can be blank) |
| ref_note | manual exit | free text; "manual" marks an expected mismatch |

`data/reference/ic_reference_legs.csv` – 4 rows per trade:
`trade_id, side (SELL/BUY), opt_type (CE/PE), strike, expiry, entry_dt, exit_dt, entry_px, exit_px`
(StockMock prices, used by the probe and as the entry fallback).

Then `python download.py` (fetches only the new data) and `python backtest.py`.

### 5.9 Offline smoke test (no API, no credentials)
Checks the whole pipeline with a fake Breeze client in a temporary folder:
```bash
python tests/smoke_test.py
```
Run it after changing the code. The fake prices are not market data.

---

### 5.10 Monthly routine (paper or live trading)
**Forward-test plan (3-Oct-2026):** 1 lot for 3–6 months with the default rules – ±2.5% 10-day filter, Monday
~11:15–11:16 entry (~43 DTE), ~30Δ CE + PE sold, 300-pt hedges, exit at −100% / +50% of credit or 18 DTE, and a
noted (not acted on) check of the condor at 15:16 on every 1% gap-up day. Later: same rules with 400-pt hedges.

The project only reads historical data – it never places orders. Each month:

1. **Evening before the planned entry (42–45 DTE):** check the 10-day trend filter – NIFTY's
   last close vs its close 10 trading days earlier. Beyond ±2.5% → skip the month.
   (`python download.py --index` then `python backtest.py` shows it as `nifty_10d_move_pct`
   once the trade is in the reference files.)
2. **Entry at 11:16:** sell the ~30-delta CE and PE, buy the hedges 300 points further out. If a
   strike has no price, use the fallback rule (spread 50/100 points closer or further, else a
   350/400-point hedge).
3. **Every day at 15:16:** exit all 4 legs at −100% of the credit (stop) or +50% (target).
   Optional (paper trade it first): if NIFTY opened ≥ 1% above the previous close that day, exit
   at 15:16 too (gap-up exit, §7). Log every such day either way.
4. **Time exit:** 15:16 on the last trading day on/before expiry − 18 days.
5. Afterwards: add the trade to the two reference CSVs (section 5.8), `python download.py`,
   `python backtest.py`, and compare your fills with the backtest.

## 6. The Excel report (`output/IC_backtest_report.xlsx`)

| Sheet | Contents |
|---|---|
| Summary | Engine gross vs engine net of costs vs StockMock: total P&L, win %, averages, max drawdown, streaks, profit factor, P&L in points, exit-reason counts, max concurrent positions, total costs, reconciliation counts, notes |
| Trades | One row per trade: dates, DTE, NIFTY 10-day move at the close before entry (`nifty_10d_move_pct`) and the filter result (`trend_filter`), strikes, entry/exit price of every leg, credit, TP/SL levels, P&L (points, % of credit, ₹ gross/net), costs, MFE/MAE at daily checks |
| Daily_MTM | Every 15:16 check: position value, P&L, action (HOLD/TARGET/STOPLOSS/GAP_UP/TIME/SKIP), price quality |
| Reconciliation | Engine vs StockMock per trade: MATCH / PNL DIFF / EXIT DIFF / SKIPPED (filter), with likely reason |
| Skipped | Months skipped by the trend filter, with NIFTY's 10-day move at the close before entry |
| Data_Quality | Every price that did not come from the exact-minute candle |

### Price quality flags

| Flag | Meaning |
|---|---|
| EXACT | close of the candle labelled with the exact minute |
| FFILL | last traded candle earlier that day (≤ 15 minutes old) |
| STALE | last traded candle earlier that day, > 15 minutes old |
| AFTER | no earlier trade that day; first candle after the target minute (slight look-ahead) |
| AFTER_TOO_LATE | entry leg's first trade came more than `MAX_AFTER_MIN_AT_ENTRY` (15) minutes after 11:16 – rejected (not knowable at entry) |
| (fallback) | a leg with no usable entry price: that side's spread moves to the nearest priced strikes – 50 closer, 50 further, 100 closer, 100 further – else the hedge widens by 50/100 points, i.e. 350/400 for 300-pt hedges (`FALLBACK_SHIFTS`, `FALLBACK_HEDGE_EXTRA`, `IC_FALLBACK=off`). Shown in the Trades sheet's `strike_note` column |
| BAD_PRICE | a hedge priced at or above its sold leg (a stray illiquid print): at entry the trade is skipped (BAD_ENTRY_PRICE); on a daily check that day is skipped; on the time-exit day the last consistent prices are used |
| REF | entry leg had no Breeze price; StockMock's entry price used |
| CARRY | forced time exit with no price that day; last known price carried forward |
| NO_TRADES | no candles that day (check skipped unless it is the time-exit day) |
| NOT_DOWNLOADED | cache file missing – run `download.py` |

### Reading the reconciliation
- **MATCH** – same exit day and reason, P&L within 3 points (`RECON_PNL_TOL_PTS`).
- **PNL DIFF** – same exit, P&L differs more (usually thin data or 1-minute timing).
- **EXIT DIFF** – different exit day/reason. The `expected?` column explains known cases:
  manual StockMock exit, different exit rule (StockMock used 15 DTE, the engine now uses 18 DTE
  – `REF_EXIT_DTE`), thin/missing prices, or P&L within 3% of the TP/SL level (tiny price
  differences can flip those).
- With 18 DTE most trades show EXIT DIFF by design. To check the engine against StockMock
  like-for-like, run with `EXIT_DTE = 15` and a separate `--out` file.

---

## 7. Known facts about the reference data

- **67 trades**, Feb-2021 to Sep-2026 expiries, all closed. StockMock gross: ₹35,258.
- **April-2026 cycle missing** – StockMock had no proper data for the strikes. Not traded.
- **Trade 23** – exited manually in StockMock at 17 DTE; the engine follows the rules and exits
  on 14-Dec-2022. Expected mismatch.
- **Trade 62** – (StockMock, 15 DTE) 15 DTE fell on a Sunday → exit Fri 13-Mar-2026 (17 DTE).
- **Trade 67** – 14-Sep-2026 was a holiday → exit Fri 11-Sep-2026 (18 DTE). The StockMock export
  had a blank exit time for this trade.
- **Muhurat sessions** (Diwali special ~1-hour session) are listed in `MUHURAT_DAYS` and treated
  as non-trading days: no 15:16 check and never a time-exit day (there is no 15:16 candle).
  With 18 DTE this moves trade 10 to Wed 3-Nov-2021 and trade 34 to Fri 10-Nov-2023.
  Add each new year's date once NSE announces it.
- **Why 18 DTE** (decided 27-Sep-2026 after testing 15–21 DTE, TP 30–70%, SL 50–100%): vs 15 DTE,
  net P&L ₹18,375 → ₹26,770, net max drawdown −₹17,878 → −₹9,286, no stop-loss hits, one condor
  at a time. 55 of 67 trades change (30 better, 25 worse); it mainly cuts the big time-exit losses.
  17 and 21 DTE were worse than 15, so treat the gain as promising, not proven – paper trade it.
  Adding a 50% SL or a 40% target on top made results worse.
- **Trade 9 (Sep-2021)** – thin data: far strikes traded rarely; expect fallback prices.
- **Lot sizes** (`config.LOT_SIZES`, by expiry): 50 up to May-2024; **25 from Jun-2024 to Jan-2025**
  (NSE cut the lot to 25 from 26-Apr-2024; the 75 lot applied only to contracts introduced from
  20-Nov-2024, so the Dec-2024 and Jan-2025 monthlies stayed at 25); 75 Feb–Dec 2025; 65 from Jan-2026.
  The original StockMock export used 50 for trades 41–48; the Summary's StockMock column now uses
  StockMock points × `LOT_SIZES` so both columns are on the same lot sizes.
- **18 DTE in practice**: with Thursday expiries (to Aug-2025) expiry − 18 days is a Sunday, so the
  time exit is the Friday before (20 DTE). With Tuesday expiries (from Sep-2025) it is 18 DTE.
- **Open positions**: with the 15-DTE exit two condors were often open together. With the 18-DTE
  exit the old condor is closed before the next entry (42–45 DTE), so only **one** is open at a time.
- **Stop-loss vs maximum loss**: with 300-pt hedges the credit is ≈ 145 pts, so the max possible
  loss is ≈ 155 pts per condor (200-pt hedges: credit ≈ 103, max loss ≈ 97). With daily-only checks
  a loss can exceed 1× credit.
- **Why 300-pt hedges** (decided 27-Sep-2026; same 61 trades, 18 DTE, SL 100%, net of costs):
  P&L ₹23,108 → ₹38,581, max drawdown −₹9,286 → −₹11,860, largest loss −₹5,834 → −₹8,529.
  300 beat 200 at every exit DTE from 15 to 22 and in 5 of 6 years. Tested and rejected for 300:
  SL 50/60/75/80%, exit 15–17 and 19–30 DTE (18–20 DTE is the best range).
- **6 trades not run with 300-pt hedges** – 24, 30, 31, 33, 57: the 300-pt CE had no trades at all
  on the entry day (a real fill risk); 1: no Breeze data on the entry day for any leg (at 200 it
  used StockMock's entry prices). Results cover 61 trades.
- **Liquidity/slippage** matter more than any rule change: 1 pt slippage per leg cuts the 300-pt
  result to ≈ ₹11k (and turns 200-pt negative). Check real bid-ask on the 300-pt hedges at 11:16
  before trading live.
- **Reconciliation** with 300-pt hedges: every row differs from StockMock by design (label
  "hedges 300 pts vs StockMock 200 pts"). For a like-for-like check run
  `IC_HEDGE_WIDTH=200` with `EXIT_DTE = 15`.
- **Why the 10-day trend filter** (adopted 28-Sep-2026): losses come from trending months – 18 of
  23 losing trades happened when NIFTY moved more than 3.3% during the trade. Skipping entries after
  a > 2.5% 10-day move (either direction) removed 12 losers and 6 winners. Backtest: 60 → 42 trades,
  net ₹38,322 → **₹64,859**, max drawdown −₹11,860 → **−₹7,243**, win rate 62% → 74%, profit factor
  1.57 → 3.46. It helped in every year except 2022, held up on 2024–26 data it was not tuned on,
  any window of 8–12 days and threshold of 2–3.5% also beat no filter, and the user's independent
  StockMock run gave the same result (≈ ₹42.7k → ₹64.2k net, drawdown −₹12.9k → −₹7.2k).
- **Other filters tested on top of it and not adopted**: India VIX level/change, VIX minus realised
  volatility (looked good grouped, failed the 2024–26 test), 50/200-day averages, 5/20-day moves,
  daily range, credit size. An election-results rule (don't hold through general/major state
  results) helped slightly on 5 trades (+₹4.7k, largest loss −₹7.2k → −₹5.5k) – a judgement rule,
  not proven.
- **Gap-up exit** (tested 2-Oct-2026, built in, **off by default**; turn on with `IC_GAP_UP_EXIT=1.0`).
  Idea (user's): gap-ups create the big losses, so close the condor at 15:16 on a day NIFTY opens
  ≥ 1% above the previous close. Results with the ±2.5% filter, net of costs:

  | Rule | 300-pt net | 300-pt max DD | 400-pt net | 400-pt max DD |
  |---|---|---|---|---|
  | No gap exit (default) | ₹66,052 | −₹7,527 | ₹83,114 | −₹9,814 |
  | Gap-up ≥ 0.75% | ₹50,661 | −₹6,656 | ₹65,170 | −₹9,643 |
  | **Gap-up ≥ 1.0%** | **₹68,023** | **−₹5,523** | **₹88,148** | **−₹6,976** |
  | Gap-up ≥ 1.25% | ₹69,073 | −₹7,217 | ₹87,107 | −₹9,814 |
  | Gap-up ≥ 1.5% | ₹68,798 | −₹7,217 | ₹87,330 | −₹9,814 |
  | Gap-up ≥ 2.0% | ₹63,585 | −₹7,527 | ₹80,776 | −₹9,814 |
  | Gap-**down** ≥ 1.0% (for comparison) | ₹47,269 | −₹12,041 | ₹58,278 | −₹16,281 |
  | Gap either way ≥ 1.0% | ₹54,918 | −₹6,110 | ₹71,100 | −₹8,255 |

  - 300-pt, gap-up ≥ 1%: 14 early exits – 4 helped (+₹13.7k: trade 35 −₹7,243 → −₹897, trade 22
    −₹3,654 → +₹528, trade 15 −₹3,347 → −₹369), 10 trimmed winners (−₹11.7k). Same number of trades,
    so no extra slippage. Every year positive (2022: −₹3,307 → +₹1,477; 2023: ₹5,447 → ₹11,793).
  - Without the trend filter it also helps: 300-pt ₹47,298 / −₹11,860 → ₹58,874 / −₹5,874.
  - Gap-**downs** must not trigger an exit – those losses usually recovered; exiting doubles the
    drawdown.
  - Cautions: helps 2021–23 (₹14.2k → ₹21.3k, DD −₹7.5k → −₹3.7k) but slightly lowers 2024–26
    (₹51.8k → ₹46.7k); 0.75% is far worse and only 1.0% clearly cuts the drawdown; much of the gain
    is trade 35; cannot be checked against StockMock (needs daily prices on gap days).
  - Status: optional rule. Paper trade it: log every gap-up ≥ 1% while a condor is open and what a
    15:16 exit would have done. Reports with it on: `output/IC_backtest_gapup.xlsx`,
    `output/IC_backtest_hedge400_gapup.xlsx`.
- **Different call/put hedge widths** (tested 2-Oct-2026, not adopted; `IC_HEDGE_WIDTH_CE/PE`). With the ±2.5%
  filter, net of costs:

  | Hedges | Net | Max DD | Worst trade | Credit | Max loss/condor | 2021–23 | 2024–26 |
  |---|---|---|---|---|---|---|---|
  | **CE 300 / PE 300 (default)** | ₹66,052 | **−₹7,527** | −₹7,243 | 146 | 154 pts | ₹14,203 | ₹51,849 |
  | CE 300 / PE 400 | ₹72,533 | −₹10,935 | −₹8,584 | 163 | 237 pts | ₹11,882 | ₹60,651 |
  | CE 400 / PE 300 | ₹70,920 | −₹11,123 | −₹10,377 | 164 | 236 pts | ₹9,346 | ₹61,574 |
  | CE 400 / PE 400 | ₹83,114 | −₹9,814 | −₹9,814 | 181 | 219 pts | ₹14,944 | ₹68,170 |

  Mixed widths earn more than 300/300 but have the **largest** drawdowns: the wider side adds ~100 pts
  of risk while only ~17 pts of credit, so the worst case (≈ 237 pts) is bigger than even 400/400.
  The side that gets tested loses more – e.g. trade 11 (Nov-2021 fall): 300/300 −₹635 at the time exit,
  CE300/PE400 stopped out at −₹8,584. Both mixes are also weaker than 300/300 in 2021–23.
- **Close only the side under pressure** (tested 2-Oct-2026, not adopted). At the 15:16 check, if the call or
  put spread alone has lost ≥ X% of the total credit, close that spread and keep the other side; target,
  stop and time exit still apply to the whole trade. With the ±2.5% filter (300-pt): no rule ₹66,052 /
  DD −₹7,527; X = 40% ₹16,846 / −₹11,494; 50% ₹30,747 / −₹12,400; 60% ₹32,013 / −₹9,011; 70% ₹20,641 /
  −₹15,988; 80% ₹37,429 / −₹12,803; 100% ₹57,704 / −₹9,777. 400-pt hedges: same pattern. It trims the
  worst loss (to about −₹4.3k at 60%) but the tested side usually recovers after the close, and the
  remaining side then gets hit on the reversal (e.g. trade 61 +₹4,814 → −₹3,712, trade 51 +₹3,900 →
  −₹4,344). At 60%: 6 trades helped (+₹11.3k), 11 hurt (−₹45.3k).
- **Lock in profit** (tested 2-Oct-2026, not adopted). Once the trade has reached +A% of the credit at a 15:16
  check, exit later if it falls back to +B% (fixed floor) or T% below its peak (trailing). With the ±2.5% filter
  the **max drawdown never changes** (−₹7,527 at 300-pt, −₹9,814 at 400-pt) – the drawdown trades never reached
  +25%. Profit effect is small and patchy: 300-pt arm 25% / floor 5% ₹73,722 (+₹7.7k, 5 lock exits, mostly
  trade 67 −₹5,523 → −₹371 and trade 55), but arm 20% / floor 10% ₹59.4k and arm 30% / floor 10% ₹63.2k are
  worse than the base ₹66,052. Arm 25% was ≥ base for every floor (300 and 400-pt); gains are all in 2024–26.
- **Entry day** (tested 2-Oct-2026, not adopted; `IC_ENTRY_SHIFT`, `IC_ENTRY_TIME`, strike sets d30_*). ~30Δ CE/PE
  chosen on the entry day, 300-pt hedges, ±2.5% filter measured from that day:

  | Entry | Net | Max DD | Worst | Win | Sep-2025+ (Tuesday weekly expiry) |
  |---|---|---|---|---|---|
  | **Monday 11:16, StockMock strikes (current)** | **₹66,052** | **−₹7,527** | −₹7,243 | 73% | 9 tr, ₹29,165 |
  | Monday 11:16, 30Δ strikes (fair baseline) | ₹65,171 | −₹8,026 | −₹7,240 | 73% | 9 tr, ₹31,330 |
  | Wednesday 11:16 (43/41 DTE) | ₹27,653 | −₹16,280 | −₹10,298 | 61% | 11 tr, ₹24,765 |
  | Previous Friday 15:16 roll (48/46 DTE) | ₹52,881 | −₹11,179 | −₹11,179 | 71% | 10 tr, ₹17,250 |

  - Monday before a Tuesday weekly expiry does **not** hurt: Monday was the best entry in that period too.
  - Wednesday is worse for two reasons: on the 41 trades both filters take it makes ₹45.7k vs ₹61.8k
    (shorter hold, fewer targets), and measured from Wednesday the filter lets in 10 months that the
    Monday filter skips (−₹18.0k, incl. trade 62 −₹10.3k) – strong moves that paused for two days.
  - Friday roll: better in 2022–23 (₹7.5k / ₹13.0k vs −₹3.7k / ₹5.3k) but much worse in 2025–26
    (trade 50 −₹9.8k stop-loss; 2026 −₹0.9k); no sign of "free" weekend theta.
  - Why 2025–26 was weak for the Friday roll (₹18.0k vs Monday ₹46.9k): about ₹20k is the filter. Measured
    on Thursday's close it misses Friday's move, so it took trades 50 (−₹9.8k) and 62 (−₹11.2k) that the
    Monday check (on Friday's close) skips. Using NIFTY's live price at 15:16 on Friday for the 10-day
    move fixes most of it: Friday roll ₹64,015 / DD −₹7,458 (2025–26 ₹36.6k) – about equal to Monday.
    The remaining ~₹8.5k is the same 13 trades doing slightly worse (3 more days held, e.g. 53, 56, 67).
  - Without the 10-day filter (66 trades each): Monday 11:16 ₹45,814 / DD −₹11,488 (StockMock strikes ₹47,298 /
    −₹11,860) vs Friday 15:16 roll ₹36,464 / −₹12,011, worst trade −₹11,179. Friday better 2021–24, worse 2025–26.
  - With the 10-day filter + 1% gap-up exit (30Δ strikes): Monday 11:16 ₹65,679 / DD −₹5,550 (filter only ₹65,171 /
    −₹8,026); Friday 15:16 roll ₹51,225 / −₹7,458 (filter only ₹64,015 / −₹7,458). The gap-up exit suits Monday but
    hurts the Friday roll: weekend gap-ups trigger exits on the first Monday (trade 53 −₹3,795) and it trims more
    winners (12 hurt vs 3 helped). Monday + StockMock strikes + gap-up: ₹68,023 / −₹5,523.
- Breeze vs StockMock prices: net credit typically within ~1.5 points; single deep-ITM legs can
  differ more but offset within the spread.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `externally-managed-environment` on pip | Activate the venv (section 3.2) |
| `Breeze login failed` | Session token expired – section 4 |
| `Request Denied: The IP address used does not match...` | Your public IP changed; update the static IP of the app, or run from a machine/VM with a fixed IP |
| `WARNING: could not fetch NIFTY daily candles` | Calendar falls back to weekdays minus `EXTRA_HOLIDAYS` and `MUHURAT_DAYS`; add known holidays there |
| `Stopped at the daily call limit` | Run again tomorrow with a new session token; progress is saved |
| Many `No Data Found` | Check one file in `output/probe/raw/` (expiry/strike format) |
| `No downloaded data found` | Run `python download.py` before `backtest.py` |
| `data/nifty_daily.csv not found` | Run `python download.py --index` (or `IC_TREND_FILTER=off`) |
| Trades not run: `NOT_DOWNLOADED (run download.py)` | Some days or fallback strikes aren't downloaded yet – run `python download.py` |
| `Strike set '...' not found` | Run `select_strikes.py` for that name first, or unset `IC_STRIKE_SET` |
| `Operation not permitted` reading a file in Downloads | macOS privacy protection – copy the file into the project folder |

---

## 9. Git

```bash
git init
git add .
git status        # confirm .env, .venv/, data/cache/ and output/ are NOT listed
git commit -m "Iron condor backtest automation: probe, downloader, engine"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

Committed: code, README, reference CSVs, StockMock exports, strike sets, validation workbook.
Not committed (see `.gitignore`): `.env`, virtual environment, downloaded candles and NIFTY/VIX
files, reports, Breeze logs (`logs/`).
Before pushing, check `git status` – `.env` and `logs/` must never appear in the list.

---

## 10. Disclaimer

Backtests on historical data do not guarantee future results. Costs in `config.py` are
approximations – verify against your broker's contract notes. This is a research tool, not
investment advice.
