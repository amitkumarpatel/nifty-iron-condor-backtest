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
| Entry | **43 DTE** (the Monday six weeks before a Tuesday expiry; `ENTRY_DTE`, `EXPIRY_WEEKDAY`), **11:16** (close of the 1-minute candle labelled 11:16). Next trading day if that Monday is a holiday. Thursday expiries (before Sep-2025) were 42–45 DTE; if NSE changes the expiry day again, update both settings |
| Legs | Sell ~30-delta CE and PE (strikes from the StockMock report); buy CE and PE **300 points** further out (`HEDGE_WIDTH`; StockMock used 200). Changed from 200 on 27-Sep-2026 – see §7 |
| Check | Combined position checked **once a day at 15:16** – no intraday monitoring |
| Target | P&L ≥ **50%** of initial credit → exit all 4 legs |
| Stop-loss | Loss ≥ **100%** of initial credit → exit all 4 legs |
| Time exit | Last trading day on/before **expiry − 18 calendar days** (holiday/weekend/Muhurat session → previous trading day). Changed from 15 DTE on 27-Sep-2026 – see §7 |
| Optional: gap-up exit | **Off by default.** If on (`GAP_UP_EXIT_PCT` / `IC_GAP_UP_EXIT=1.0`): on a day NIFTY opens ≥ 1% above the previous close, exit all 4 legs at that day's 15:16 check (never on the entry day). Tested 2-Oct-2026 – see §7 |
| Sizing | **1 lot** at each expiry's NIFTY lot size (50 → 25 → 75 → 65, `LOT_SIZES`) |
| Not allowed | Adjustments, re-entry, quantity change, other entry filters |

Order of checks each day: stop-loss → target → time exit.

> **Note – 1% gap-up is an early warning (call side).** In 5 of the 7 trades where NIFTY later closed above
> the bought call – all 7 ended in a loss – NIFTY had first opened ≥ 1% above the previous close, 10 days to
> 3 weeks earlier. Exiting at the 15:16 check on such a gap-up day reduced the max drawdown from −₹7.5k to
> −₹5.5k and raised net profit from ₹66,052 to ₹68,023 (300-pt hedges, ±2.5% filter). The other 2 (trades 30,
> 52) were slow rallies with no 1% gap; there the late warning is NIFTY closing above the bought call.
> The rule is built in but **off by default** (`IC_GAP_UP_EXIT=1.0`); in the forward test it is noted, not acted on.

---

## 1a. Key lessons – read before testing anything new

All figures: Monday 11:16 entry, ~30Δ sold legs, 18-DTE exit, 50% target, 100% stop, net of costs, Feb-2021 to
Sep-2026. Details and tables for each point are in §7.

**The three things to remember**

1. **Call side: once NIFTY closes above the bought call (the hedge), the trade is a loser.** 7 of 7 such trades
   ended in a loss (−₹32.9k); with the ±2.5% filter 4 of 4 (−₹18.0k). A 1% gap-up is the *early* warning – it came
   first in 5 of those 7. The other 2 (trades 30, 52) were slow rallies with no gap.
2. **Put side: no rule separates losers from winners.** After NIFTY closed below the sold put, 20 of 28 trades
   still ended in profit; below the bought put it was 8 of 16. Every put-side exit tested roughly doubled the
   drawdown. Falls usually bounce – leave the put side to the stop-loss and the time exit.
3. **400-pt hedges earn more with a bigger drawdown – same strategy, more risk.** With the ±2.5% filter:
   300-pt ₹66,052 / max DD −₹7,527; 400-pt ₹83,114 / −₹9,814 (worst case per condor ≈ 154 vs 219 points). The 1%
   gap-up exit helps both: 300-pt ₹68,023 / −₹5,523; 400-pt ₹88,148 / −₹6,976.

**Already tested – no need to repeat**

| Idea | Result |
|---|---|
| ±2.5% 10-day filter | **Adopted.** ₹47.3k / −₹11.9k → ₹66.1k / −₹7.5k. ±3% is next best; ±2.75% and ±4% worse. The up-move (call) side does the work; only 3 trades ever started after a > 2.5% fall |
| 10Δ sold legs + 500-pt hedges in the months the filter skips | **No.** 11 of 21 months runnable (far call hedge has no price in the rest): 6 stop-losses, −₹15.2k vs −₹9.2k for 30Δ on the same months |
| Skipped month: re-check the filter the next Monday and enter then (delayed entry) | **No.** 12 months: 5 profit / 7 loss, −₹23.0k (original entry −₹19.7k, skipping ₹0) |
| Exit at 21 DTE (the common online rule) instead of 18, with the filter | **No.** ₹52.8k vs ₹66.1k, same drawdown; 18 DTE already exits on the Friday ≈ 20 DTE for Thursday expiries |
| 40Δ sold legs with 200 or 300-pt hedges | **No.** With filter ₹43.9k (300-pt) / ₹23.8k (200-pt) vs ₹66.1k; the 50% target is never reached and the stop cannot trigger |
| Same rules on 2019–2020 (years not used to choose the rules) | **Loses.** With filter −₹7.6k on 15 trades, max DD −₹18.8k; no filter −₹34.1k. Plan for ≈₹19k drawdown per lot |
| Credit/width filter: trade only if credit ≥ 48% of the 300-pt width | **Promising, not adopted.** Alone: ₹40.3k / DD −₹9.4k (2021–26), +₹5.9k in 2019–20. With the 10-day filter: ₹40.3k / DD −₹4.0k, 26 trades. Threshold is sharp (46–47% no benefit) |
| Two-tier rule: credit ≥ 48% with 10-day move within ±2.5%, or credit < 48% only if within ±1% | **Discarded by the user 8-Oct-2026.** On paper 2019–26: 41 trades ₹70.8k / DD −₹5.5k, but fitted – the 1% limit is a knife edge (1.25% lets the Feb-2020 stop back in) |
| 400-pt hedges with ±2.5% AND credit ≥ 46% of width | **Lowest drawdown found, not adopted.** 19 trades ₹52.6k / DD −₹3.0k (2021–26); stable for credit 45–46.5% and move limit 2–3%. About 3 trades a year; 2019–20 barely tests it |
| Switch hedge width by credit: 400-pt when credit ≥ 42% of 400, else 300-pt (inside ±2.5%) | **Promising, not adopted.** 2021–26: ₹84.6k / DD −₹7.4k (400-pt profit, 300-pt drawdown). 2019–20 still loses (−₹3.6k / −₹16.5k) because thin months are traded; skipping them instead gives 2019–26 ₹85.3k / −₹7.0k |
| Early exit of losing trades (loss stop at day N, NIFTY-move exit), lower/stepped target, extra hedge on a breach | **No.** All worse or no gain on 400-pt: breaches usually revert before the exit; 7 of the 10 worst trades were still flat or in profit at day 10 |
| Credit spread in skipped months (put spread after a rise, call spread after a fall; own TP 50%, SL 100% or 200%) | **No.** 2021–26: −₹11.2k (SL 100%) / −₹18.5k (SL 200%); 2019–26 about break-even. Put spread after a rise worked in 2019–23, lost in 2024–26; call spread after a fall is the wrong side |
| 1% gap-up exit at 15:16 | **Helps** (optional, off by default). Gap-*down* exits are harmful. 1.25%/1.5% give ≈ same profit, keep more of 2024–26 (+₹3k) but lose the drawdown cut (−₹7.2k, trade 35) |
| Exit when NIFTY closes above the bought call | Small help alone; adds nothing once the gap-up exit is on |
| Exit day | 18–20 DTE best; 15–17 and 21+ worse |
| Stop-loss 50–80%, target 40–60% | All worse than 100% / 50% |
| Hedge width 200 / 300 / 400, mixed call/put widths | Same profit ÷ drawdown (≈ 8–9); mixed widths have the worst drawdown |
| 25-delta call | Mixed; thin strikes; not adopted |
| VIX filters, 5/20-day moves, 50/200-day averages, range, credit size | No reliable signal |
| Election / Budget / US-election filters | Elections: judgement call only. Budget months were all winners – never skip them |
| Shift strikes with the trend, close only the tested side, lock in profit | All worse or no drawdown benefit |
| Entry day | Monday 11:16 best. Wednesday much worse. Previous-Friday 15:16 roll ≈ Monday only with the filter on live NIFTY, and it does not work with the gap-up exit |

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
| `python fetch_index_nse.py --from 2018-11-01 --to 2020-08-14` | NIFTY and India VIX daily prices from NSE's website, merged into the daily files and the calendar | No (NSE website) | `data/nifty_daily.csv`, `data/india_vix_daily.csv` |
| `python make_trades.py --from 2019-01 --to 2020-12 --name 2019_2020` | Generate monthly trades for years without StockMock data (§5.3d) | No | `data/reference/ic_trades_<name>.csv`, `ic_legs_<name>.csv` |
| `python select_strikes.py --ce-delta 0.25 --name ce25` | Experiment: choose sold strikes by delta | Yes | `data/strike_sets/` |
| `python select_strikes.py --ce-delta 0.10 --pe-delta 0.10 --around 3 --step 100 --name d10` | Same, searching around a Black-Scholes estimate of the strike (few calls; for deltas far from 30) | Yes | `data/strike_sets/` |
| `python download.py --strike-set d10 --hedge 500 [--dry-run]` | Candles for a variant: sold strikes from a strike set, hedges N points out. `--dry-run` only counts the calls (no login) | Yes (no with `--dry-run`) | `data/cache/` |
| `python backtest.py --strike-set d10 --hedge 500 [--filter off]` | Backtest a variant; report gets its own name | No | `output/IC_backtest_d10_h500[_nofilter].xlsx` |

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
| `IC_CE_BREACH_EXIT` | `off` | `hedge` (or points above the sold call, e.g. `300`): exit at 15:16 on a day NIFTY closes at/above that level |
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

### 5.3c Testing a variant: any sold delta, any hedge width
Three steps – choose the sold strikes, download their candles, backtest. The variant options work on
`download.py`, `backtest.py` and `export_prices.py` and need no environment variables:

| Option | Meaning | Same as |
|---|---|---|
| `--strike-set NAME` | sold strikes from `data/strike_sets/strikes_NAME.csv` | `IC_STRIKE_SET` |
| `--hedge N` | bought legs N points beyond the sold legs (200, 300, 400, 500 …) | `IC_HEDGE_WIDTH` |
| `--filter off` / `--filter 3` | switch the 10-day filter off or change its limit | `IC_TREND_FILTER` |
| `--entry-shift D` | enter D calendar days after the reference entry (next trading day if a holiday); also on `select_strikes.py`, so the strikes are chosen on that day | `IC_ENTRY_SHIFT` |

```bash
# 1. sold strikes at 10 delta (API, entry-day candles only)
python select_strikes.py --ce-delta 0.10 --pe-delta 0.10 --around 3 --step 100 --name d10 --dry-run
python select_strikes.py --ce-delta 0.10 --pe-delta 0.10 --around 3 --step 100 --name d10
# 2. candles for those strikes with 500-point hedges (API)
python download.py --strike-set d10 --hedge 500 --dry-run
python download.py --strike-set d10 --hedge 500
# 3. backtest (offline) -> output/IC_backtest_d10_h500_nofilter.xlsx
python backtest.py --strike-set d10 --hedge 500 --filter off
```
- `--around N` searches N strikes each side of a Black-Scholes estimate of the target-delta strike (from the
  entry spot and the implied volatility of StockMock's sold strike, both already cached) and extends the
  window up to 4 times if the target is outside it. For 10 delta this needs about 750 calls for all trades
  instead of about 4,100 with `--range 2000`. `--step 100` restricts the candidates to 100-point strikes,
  which are the liquid ones far from the money.
- One strike set serves several hedge widths: run steps 2–3 again with another `--hedge`.
- `--trades ...` limits every step to some trades (e.g. only the months the filter skips).
- Without `--out`, a variant report is named `IC_backtest_<set>_h<width>[_nofilter].xlsx`, so the main
  report is never overwritten. All other rules (11:16 entry, 15:16 check, TP 50%, SL 100%, 18 DTE) stay.

### 5.3d Testing other years (a generated trade set)
The reference trades start in Jan-2021 (StockMock). For earlier years the trades are generated with the same
pattern – one condor per monthly expiry, entered on the Monday six weeks before it – and the strikes are
picked from Breeze prices:

```bash
# 1. NIFTY + India VIX daily history from NSE's website (no login) -> filter, calendar, starting strikes
python fetch_index_nse.py --from 2018-11-01 --to 2020-08-14
# 2. the trades: entry months Jan-2019 .. Dec-2020 -> data/reference/ic_trades_2019_2020.csv (+ legs)
python make_trades.py --from 2019-01 --to 2020-12 --name 2019_2020
# 3. ~30-delta sold strikes at 11:16 on each entry day (API)
python select_strikes.py --trade-set 2019_2020 --ce-delta 0.30 --pe-delta 0.30 --around 4 --name d30_2019_2020
# 4. candles (API), then the backtest (offline)
python download.py --trade-set 2019_2020 --strike-set d30_2019_2020 --dry-run
python download.py --trade-set 2019_2020 --strike-set d30_2019_2020
python backtest.py --trade-set 2019_2020 --strike-set d30_2019_2020
```
- `--trade-set NAME` (= `IC_TRADE_SET`) works on every script; the report is named
  `IC_backtest_<trade set>_<strike set>_h<width>.xlsx`. Trade id = YYMM of the entry month (1901 = Jan-2019).
- A generated set has no StockMock prices, so there is no reconciliation (status `NO REFERENCE`) and no
  StockMock fallback price at entry.
- `make_trades.py` was checked against the reference trades: it reproduces all 66 entry and expiry dates.
- `fetch_index_nse.py` only adds days that are missing (use `--replace` to overwrite) and also extends the
  trading calendar. `download.py --index` now merges too, so it no longer drops earlier history.
- Lot size for expiries up to Jan-2021 is 75 (`LOT_SIZES`).

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

1. **Evening before the planned entry (43 DTE, the Monday six weeks before the Tuesday expiry):** check
   the 10-day trend filter – NIFTY's last close vs its close 10 trading days earlier. Beyond ±2.5% → skip
   the month. The forward-test helper does this from NSE's website, no Breeze login needed:
   `python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py plan --expiry YYYY-MM-DD` (entry and
   time-exit dates), then `... ic_tools.py filter --entry-date YYYY-MM-DD --show` (TRADE or SKIP).
   It falls back to `data/nifty_daily.csv` with a warning if NSE cannot be reached.
   NSE holidays for the entry/exit dates are kept in `NSE_HOLIDAYS` (`ic/config.py`); refresh them each
   January with `... ic_tools.py holidays --write` (reads the F&O holiday list from NSE's website). Monthly
   expiries move to the previous trading day when the Tuesday is a holiday (Nov-2026 expiry = Mon 23-Nov).
   (`python download.py --index` then `python backtest.py` shows the same value as `nifty_10d_move_pct`
   once the trade is in the reference files.)
2. **Entry at 11:16:** sell the ~30-delta CE and PE, buy the hedges 300 points further out.
   `... ic_tools.py strikes --expiry YYYY-MM-DD` reads NSE's option chain and prints the strikes nearest
   30 delta, the four legs with bid/ask, the credit, target, stop and maximum loss (NSE's chain lags a few
   minutes – confirm prices in the broker terminal). If a
   strike has no price, use the fallback rule (spread 50/100 points closer or further, else a
   350/400-point hedge).
3. **Every day at 15:16:** exit all 4 legs at −100% of the credit (stop) or +50% (target).
   Optional (paper trade it first): if NIFTY opened ≥ 1% above the previous close that day, exit
   at 15:16 too (gap-up exit, §7). Log every such day either way.
4. **Time exit:** 15:16 on the last trading day on/before expiry − 18 days.
5. Afterwards: add the trade to the two reference CSVs (section 5.8), `python download.py`,
   `python backtest.py`, and compare your fills with the backtest.

## 5a. Claude skill

The repo carries one Claude skill, `nifty-ic-forward-test`, in `.claude/skills/nifty-ic-forward-test/`
(`SKILL.md`, `scripts/ic_tools.py`, `assets/forward_trades_template.csv`). Claude Code loads it in sessions opened
in this folder when you mention the iron condor, the forward test, the 10-day filter or the 15:16 check. It runs
the monthly routine of §5.10 as a paper-trading workflow. The same commands can be run by hand:
`python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py <command>`.

**What Claude can do with it**

| You ask | What Claude does | Command |
|---|---|---|
| "What are the current rules?" | Prints the live values from `ic/config.py`, including entry DTE (43) and expiry weekday (Tue) | `rules` |
| "Plan the November cycle" | Gives one entry date (the Monday six weeks before expiry) and the time-exit date, using the NSE holiday list in config; prints a note when the expiry is not a Tuesday and a warning when a year has no holiday list | `plan --expiry` |
| "Should I enter this month?" | Reads the last 11 NIFTY closes from NSE's website and reports the 10-day move with TRADE or SKIP; uses `data/nifty_daily.csv` only if NSE is unreachable | `filter --entry-date` |
| "Refresh the NSE holidays" | Shows NSE's F&O holiday list and what would change; with your agreement, writes it into `NSE_HOLIDAYS` in `ic/config.py` | `holidays [--write]` |
| "Which strikes for this expiry?" | Reads NSE's option chain, finds the strikes nearest 30 delta, adds the 300-point hedges (with the fallback rule), and prints bid/ask, credit, target, stop and maximum loss | `strikes --expiry` |
| "Log today's check" | Takes the four 15:16 leg prices and reports HOLD, TARGET, STOPLOSS, TIME or GAP_UP; fetches the previous close from NSE if it is not given; logs to `journal/forward_daily.csv` | `check --log` |
| "The trade is closed" | Prints the rows for the two backtest reference files; writes nothing until you agree | `export-ref` |

**Rules Claude follows under the skill**

- No orders: only read-only tools on a broker connector; it never places, modifies or cancels orders or GTTs.
- No recommendations: it reports what the rules and numbers say; the strikes and the decision to trade are yours.
- `ic/config.py` and this README are the source of truth; it reads the values with `rules` each session.
- `holidays --write` is the only command that edits `ic/config.py`, and only after showing the difference.
- If NSE changes the expiry day it stops, because `ENTRY_DTE` and `EXPIRY_WEEKDAY` must be updated first.
- `journal/` is git-ignored, so the forward-test records stay on your machine (keep your own backup).

**What it does not do**

- It does not run on a schedule or send alerts; each check happens when you ask.
- It does not fetch the 15:16 leg prices or today's NIFTY open by itself; you give them, or Claude reads them from
  a read-only broker connector.
- NSE's website option chain lags a few minutes, and NSE can change or block these addresses.

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
  exit the old condor is closed before the next entry (42–45 DTE in the backtest, 43 DTE going forward), so only **one** is open at a time.
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
  - Gap level 1% vs 1.25% vs 1.5% by period (4-Oct-2026, 300-pt, filter; base 2021–23 ₹14,203 / 2024–26 ₹51,849):
    1% ₹21,333 / ₹46,689; 1.25% ₹19,270 / ₹49,803; 1.5% ₹19,150 / ₹49,648. In 2024–26 the 1% rule made 5 exits
    (−₹5,160): trade 56 ₹5,631 → ₹2,843 (gap 1.03%) and trade 43 ₹1,475 → ₹1,149 (1.24%) are saved by 1.25%;
    trade 61 ₹4,814 → ₹2,901 (4.69% gap) and trade 41 (3.58%) are cut at every level. No 2024–26 loss was avoided
    by any level. But 1.25%/1.5% lose the drawdown benefit: trade 35's first gap-up was 1.09% (15-Nov-23, exit
    −₹897); the next was 1.71% on 4-Dec-23, one day before the stop (−₹6,933). The whole 1% vs 1.25% choice
    rests on trades 35 (+₹6.0k for 1%) and 56/3 (+₹5.8k for 1.25%) – too few to tune; keep 1% as the level.
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
- **Separate CE / PE filter limits** (3-Oct-2026). Up-move (CE side) limit drives the result; only 3 trades ever
  started after a 10-day fall > 2.5% (17, 46, 52). CE 2.5% / PE 2.5% ₹66,052 / −₹7,527; CE 3% / PE 2.5% ₹62,516 /
  −₹8,529 (trade 62 comes back). Removing trade 62 by hindsight makes CE 3% / PE 2.5% look best (₹71,045 / −₹7,243),
  but with the 1% gap-up exit applied to every trade both are equal (₹68,023 vs ₹68,159, DD −₹5,523), and a gap
  exit in both directions makes CE 3% worse (₹57,045 / −₹8,993). Kept 2.5% on both sides.
  Skipped months by side (4-Oct-2026, list in `output/filter_skipped_trades_CE_PE.xlsx`): after a rise > 2.5% – 18 trades,
  8 profit / 10 loss, −₹15,061 (6 lost on the call side as the rally continued, −₹17.3k; 4 on the put side after a reversal,
  −₹18.0k). After a fall > 2.5% – 3 trades (17, 46, 52), −₹3,694.
  Skipped months – 10-day move on the next 10 trading days (4-Oct-2026, output/skipped_trades_next_10day_move.xlsx): the reading is
  back inside ±2.5% after 1 day in 8 of 21, within 3 days in 13, within 8 days in all (median 2); average after a rise 3.75% →
  1.57% (day 5) → −0.33% (day 10). But it often leaves the band again (16, 48, 50 to the down side; 5, 19, 63 back up), and the 4
  reversal losers (62, 16, 48, 50) were all back inside within 1–2 days – "enter as soon as it is back inside" would re-take them.
  10Δ + 500-pt hedges in the filter-skipped months (5-Oct-2026, strike set d10, output/IC_backtest_d10_h500_nofilter.xlsx), NOT
  adopted: only 11 of 21 months could be run – in the other 10 the call hedge 500 pts beyond the 10Δ call had no price at 11:16
  (strikes 300+ pts beyond a 10Δ call mostly do not trade 6 weeks out; puts are fine). The 11 that ran: 5 target / 6 stop-loss,
  net −₹15,235 vs −₹9,185 for the 30Δ/300-pt condor on the same months. Credit only ≈50 pts (30Δ ≈141), so the 100% stop sits
  close: stops at 1.0–1.7× credit (−₹1.5k to −₹4.9k) against ≈₹1–1.8k per win. Not an alternative for skipped months.
  Delayed entry for skipped months tested 5-Oct-2026, NOT adopted (re-check the filter the next Monday, enter a fresh 30Δ/300-pt
  IC at 35–38 DTE if inside ±2.5%; strike set d30_nm, --entry-shift 7): 13 of 21 months qualify; 12 run (trade 20 not downloaded):
  5 profit / 7 loss, net −₹22,988 (same months at the original entry −₹19,742; skipping = ₹0). 3 stop-losses (62 −₹11.4k,
  12 −₹6.8k, 8 −₹6.5k); helped 50, 9, 16, hurt 12, 5, 62. A calm reading one week later does not make these months safe.
  Exit-DTE ladder WITH the ±2.5% filter (5-Oct-2026, 300-pt, 45 trades; net / max DD): 17 ₹64,819 / −₹11,416; 18 ₹66,052 / −₹7,527;
  19 ₹62,376 / −₹7,527; 20 ₹58,490 / −₹7,527; 21 ₹52,829 / −₹7,243; 22 ₹43,972 / −₹7,243; 23 ₹37,508 / −₹9,880; 25 ₹34,074 / −₹7,332.
  The popular "exit at 21 DTE" costs ₹13.2k for no drawdown gain: for Thursday expiries 18 DTE already means Friday = 20 DTE, and
  21 DTE is one day earlier (Thursday); for Tuesday expiries it is 3 trading days earlier. Fewer targets reached (11 → 4). Keep 18.
  "45 DTE entry" = what the backtest did with Thursday expiries (Monday = 45 DTE); 43 DTE is the same Monday for Tuesday expiries.
  40Δ sold legs tested 5-Oct-2026, NOT adopted (strike set d40, all 66 trades; output/IC_backtest_d40_h300[_nofilter].xlsx,
  IC_backtest_d40_h200[_nofilter].xlsx). With the ±2.5% filter, same 45 trades (net / max DD / win / PF): 30Δ+300 ₹66,052 / −₹7,527 /
  73% / 3.20; 40Δ+300 ₹43,912 / −₹6,186 / 69% / 2.64; 40Δ+200 ₹23,838 / −₹5,585 / 64% / 2.16 (30Δ+200 ₹42,911 / −₹4,695). No filter:
  40Δ+300 ₹23,673 / −₹12,171; 40Δ+200 −₹1,699 / −₹19,423 (30Δ+300 ₹47,298 / −₹11,860). 0.5-pt slippage: 40Δ+300 ₹34.4k, 40Δ+200 ₹14.3k.
  Why: credit is 203 of 300 pts (141 of 200), so the 50% target (≈100 pts) was never reached – 0 targets vs 11 – and the 100% stop
  is beyond the maximum loss, so it cannot trigger; every trade is a time exit. Worse in every year. TP/SL as % of credit do not
  fit 40Δ; a fair retest would need its own TP/SL (not done).
  2019–2020 OUT-OF-SAMPLE RUN (7-Oct-2026; trade set 2019_2020, strike set d30_2019_2020, lot 75; Breeze has the data;
  output/IC_backtest_2019_2020_d30_2019_2020_h300[_nofilter].xlsx). Same rules (30Δ, 300-pt, TP 50%, SL 100%, 18 DTE).
  With the ±2.5% filter: 15 trades, net −₹7,579, max DD −₹18,795, worst −₹11,002, win 67%, PF 0.76 (2019 −₹1,242, 2020 −₹6,337);
  0 targets, 2 stop-losses: 2002 (entry 10-Feb-2020, COVID crash, −₹11,002) and 1907 (Jul-2019, NIFTY −6.3%, −₹9,478); 1903
  (Mar-2019 rally +4.5%, −₹6,770). No filter: 23 trades −₹34,106 / DD −₹40,887 (2003 crash month −₹18,732; 2004 not run – no
  price). The filter still helps (+₹26.5k) but does not make these years profitable. Gap-up 1% exit makes it worse (−₹9,808 /
  DD −₹22,923). 2019–2026 with filter: 60 trades ₹58,472, max DD −₹18,795, win 72%, PF 1.95 (2021–26 alone: ₹66,052 / −₹7,527 /
  PF 3.20). LESSON: plan for a drawdown of ≈₹19k per lot, not ₹7.5k; a fast 6–9% fall hits the stop even from a calm start.
  Caveats: 300 pts ≈ 2.5–3.5% of NIFTY then (1.2% now); thinner 2019–20 option data (many FFILL/STALE prices).
  2019–2020 four-way (7-Oct-2026, net / max DD / worst): no filter −₹34,106 / −₹40,887 / −₹18,732; gap-up 1% only −₹20,363 / −₹27,144 /
  −₹9,478; ±2.5% filter −₹7,579 / −₹18,795 / −₹11,002; filter + gap-up −₹9,808 / −₹22,923 / −₹9,478. Gap-up alone helps (+₹13.7k) but
  ₹12.2k of that is the Mar-2020 crash month (2003: a 1.35% bounce on 18-Mar got it out early) – it worked as a crash exit, not as
  a call-side rule. On the 15 filtered trades it costs ₹2.2k (1909: 2.38% gap on the 20-Sep-2019 tax-cut rally, +₹304 → −₹5,248).
  2019–2020 with 400-pt hedges (7-Oct-2026, output/IC_backtest_2019_2020_d30_2019_2020_h400[_nofilter].xlsx; net / max DD / worst):
  filter 400-pt −₹4,531 / −₹20,046 / −₹12,430 (PF 0.88) vs 300-pt −₹7,579 / −₹18,795 / −₹11,002 (PF 0.76); no filter 400-pt −₹22,170 /
  −₹31,189 vs 300-pt −₹34,106 / −₹40,887 (the two no-filter runs differ in one month: 1905 / 2004). Same pattern as 2021–26: wider
  hedges = bigger wins (+₹10.6k on 10 winners) and bigger losses (−₹7.6k on 5 losers; 1907 −₹9.5k → −₹12.4k). Still a losing period.
  2019–2026 with filter: 300-pt 60 trades ₹58,472 / DD −₹18,795 / PF 1.95; 400-pt 59 trades ₹78,583 / DD −₹20,046 / PF 2.02.
  Credit/width filter (user idea, 7-Oct-2026; trade only if net credit >= 48% of the 300-pt width = 144 pts; 300-pt, net / max DD /
  worst / PF). 2021–26 (66 trades): no filter ₹47,298 / −₹11,860; ±2.5% 10-day 45 tr ₹66,052 / −₹7,527 / −₹7,243 / 3.20; credit>=48%
  38 tr ₹40,295 / −₹9,434 / −₹5,345 / 2.49; BOTH 26 tr ₹40,271 / −₹4,003 / −₹3,731 / 4.72. 2019–20: 10-day −₹7,579 / −₹18,795; credit>=48%
  5 tr +₹5,889 / −₹1,688; both 3 tr +₹3,801. 2019–26: 10-day 60 tr ₹58,472 / −₹18,795 / PF 1.95; credit>=48% 43 tr ₹46,184 / −₹9,434 /
  2.61; both 29 tr ₹44,072 / −₹4,003 / 4.52. No stop-loss in 8 years with credit>=48%. Skips the 2019–20 losers (1903 36%, 1907 37%,
  2002 39%) and 62/35/67 (47.1/46.2/47.0%). CAVEATS: threshold is sharp – 46% gives no benefit (DD −₹10.2k), 47% −₹10.2k, 49% −₹6.1k,
  50% −₹4.6k (22 tr); the three big 2021–26 losers sit just under 48. On its own it is worse than the 10-day filter in 2021–26
  (skips 19 filtered trades worth +₹25.8k incl. 6 targets). Ratio rises with VIX (corr 0.37) = sell only when premium is rich.
  Not adopted yet – candidate to shadow-log in the forward test (credit/width at entry).
  Credit/width at 47.5% (7-Oct-2026): ≈ same as 48%. 2021–26 alone 41 tr ₹41,320 / DD −₹10,209 (48%: 38 tr ₹40,295 / −₹9,434); with the
  10-day filter 28 tr ₹40,101 / −₹4,712 / PF 3.77 (48%: 26 tr ₹40,271 / −₹4,003 / 4.72). Only trades 22 (47.58%, −₹3,654), 27 (47.63%,
  +₹3,483) and 12 (47.88%, +₹1,195) change; 2019–20 identical (5 tr +₹5,889). 47.0% lets trade 62 (47.13%, −₹8,529) and 2006 back in.
  The useful line is anywhere from 47.2% to 48% – decided by 3–4 trades; do not tune finer.
  Credit/width split by side (7-Oct-2026; CE ratio = (sold CE − bought CE)/300, PE likewise; 2021–26 averages CE 26.4%, PE 22.1%), NOT
  useful. A side's credit does not predict that side's result (correlation −0.01 CE, −0.04 PE). CE-only limits cut profit with no
  DD gain (CE>=24%: ₹31.9k / −₹10.7k). PE-only looks good in 2021–26 (PE>=23%: 17 tr ₹20.8k / −₹4.6k) but loses in 2019–20 (−₹4.6k;
  PE>=25% −₹10.9k). Two-sided grids over 2019–26: CE>=23 & PE>=21 ₹46.9k / −₹12.6k; CE>=25 & PE>=22 ₹42.3k / −₹9.3k; CE>=26 & PE>=22
  ₹37.8k / −₹6.1k – none beats the single total>=48% rule (₹46.2k / −₹9.4k) and neighbouring cells jump around. The 2019–20 put-side
  losers (2002, 1907) had normal put credit and very low CALL credit (17.7%, 15.5%), so only the total caught them. Keep the total.
  Second filter with credit/width (7-Oct-2026, search over 10-day move, 5/20-day moves, VIX level, VIX − realised vol; 300-pt; net / max
  DD). AND-filters on top of credit>=48% do not add profit (best: & |10d|<=2.5% ₹40.3k / −₹4.0k in 2021–26). What adds profit is a
  TWO-TIER rule that brings back thin-credit months only when the market is very calm:
    trade if (credit>=48% and |10d move|<=2.5%) OR (credit<48% and |10d move|<=1%).
  2021–26: 34 tr ₹58,661 / −₹5,523 / PF 4.59 (10-day only 45 tr ₹66,052 / −₹7,527); 2019–20: 7 tr +₹12,122 / −₹1,688 (10-day only
  −₹7,579 / −₹18,795); 2019–26: 41 tr ₹70,782 / −₹5,523 / PF 4.92, no stop-loss, no losing year, 0.5-pt slip ₹61.7k (10-day only
  ₹58,472 / −₹18,795 / ₹44.4k). Without the 2.5% cap on rich-credit trades: 55 tr ₹72,894 / −₹9,434.
  WARNING – fitted after seeing all the data: the 1% limit is a knife edge. At 1.25% trades 1910 (−1.18%, −₹2.6k) and 2002 (−1.22%,
  COVID stop −₹11.0k) come in and 2019–20 falls to −₹1.5k / DD −₹12.7k; at 1.5% 2021–26 rises to ₹66.3k. Credit line 47.25–50%
  all similar. NOT adopted. Honest test = years never looked at (2017–18 if Breeze has them) or forward shadow-logging.
  VIX level, VIX − realised vol, 5-day and 20-day moves as the second filter: no consistent gain in both periods.
  Two-tier rule on 400-pt hedges, 2021–26 (7-Oct-2026, output/filter_comparison_2021_2026_hedge400.xlsx; net / max DD / PF): no filter
  65 tr ₹61,439 / −₹14,946 / 1.68; ±2.5% 10-day 44 tr ₹83,114 / −₹9,814 / 3.17; two-tier 33 tr ₹74,434 / −₹6,976 / 4.64 (credit line
  45% of the 400-pt width = the same richness as 48% of 300; using the 300-pt condor's 48% as the signal: 34 tr ₹76,228 / −₹6,976).
  48% of 400 is too strict (two-tier 25 tr ₹64,970; credit alone 12 tr). Same picture as 300-pt (₹66,052 / −₹7,527 → ₹58,661 /
  −₹5,523): ≈ ₹7–9k less profit, ≈ ₹2–3k less drawdown, 11 fewer trades, no stop-loss. 300-pt file: output/filter_comparison_2021_2026.xlsx.
  User leans towards the two-tier rule (7-Oct-2026); not yet adopted in config – still fitted, see warning above.
  Trade 60's 18-Dec-2025 candles for the 200 and 400-pt hedges were downloaded 7-Oct-2026; 400-pt results unchanged.
  300 vs 400-pt under each single filter (8-Oct-2026; net / max DD / worst / PF). 2021–26: 300 ±2.5% 45 tr ₹66,052 / −₹7,527 / −₹7,243 /
  3.20; 400 ±2.5% 44 tr ₹83,114 / −₹9,814 / −₹9,814 / 3.17; 300 credit>=48% 38 tr ₹40,295 / −₹9,434 / −₹5,345 / 2.49; 400 credit>=46% 28 tr
  ₹49,944 / −₹10,102 / −₹6,954 / 3.32. 2019–20: 300 ±2.5% −₹7,579 / −₹18,795; 400 ±2.5% −₹4,531 / −₹20,046; 300 credit>=48% 5 tr +₹5,889 /
  −₹1,688; 400 credit>=46% 3 tr −₹2,604 / −₹11,055 (2011: −₹9,068). 2019–26: 300 ±2.5% ₹58,472 / −₹18,795; 400 ±2.5% ₹78,583 / −₹20,046;
  300 credit>=48% ₹46,184 / −₹9,434; 400 credit>=46% 31 tr ₹47,339 / −₹11,055. 400-pt DD is ≈ ₹1–2.5k (10–30%) deeper than 300-pt
  under either filter; its worst trade ≈ 30% bigger (max loss/condor 219 vs 154 pts). Credit-only on 400 is not robust: 45%
  −₹14,509 DD, 46% −₹10,102, 47% −₹6,074, and it did not hold in 2019–20 the way 48% on 300 did.
  Both filters together (±2.5% AND credit/width), 2021–26 (8-Oct-2026; net / max DD / worst / PF): 300-pt & >=48% 26 tr ₹40,271 / −₹4,003 /
  −₹3,731 / 4.72 (±2.5% alone 45 tr ₹66,052 / −₹7,527); 400-pt & >=46% 19 tr ₹52,633 / −₹2,989 / −₹1,558 / 13.9 (±2.5% alone 44 tr ₹83,114 /
  −₹9,814). 400-pt line is sensitive: & >=45% 23 tr ₹58,379 / −₹4,407 (trade 15 at 45.6% comes in), & >=48% 8 tr ₹24,197 / −₹1,430.
  Roughly 3 trades a year at 400-pt – tiny sample; not run on 2019–20 for 400-pt (300-pt both: 3 tr +₹3,801).
  400-pt filter tuning (8-Oct-2026, user's pick = ±2.5% AND credit>=46% of 400; n / net / max DD; 2021–26 | 2019–20 | 2019–26):
  ±2.5 & 46%: 19 ₹52,633 −₹2,989 | 1 −₹1,986 | 20 ₹50,647 −₹2,989.   ±2.5 & 45%: 23 ₹58,379 −₹4,407 | 2 +₹3,821 | 25 ₹62,200 −₹4,407.
  ±2 & 45%: 18 ₹55,772 −₹1,558 | 2 +₹3,821 | 20 ₹59,593 −₹1,986.     ±2 & 46%: 17 ₹52,127 −₹1,558.   ±3 & 46%: 20 ₹55,045 −₹2,989.
  Stable plateau: credit 45–46.5% × move limit 2–3% all give ₹52–58k with DD −₹1.6k to −₹4.4k (the only swing trade is 15: 45.6%,
  +2.49%, −₹4,407). Beyond ±3% or below 45% the DD jumps to −₹7k…−₹15k. The UP limit is what matters (no up limit: DD −₹13k); the
  down limit hardly matters. Gap-up exit on top: no gain (₹44.4k / −₹3.5k). Two-tier form (rich ±2.5 / thin ±1) at 46%: 30 tr
  ₹72,333 / −₹6,976 | 7 tr +₹18,831 | 37 tr ₹91,165 / −₹6,976, but thin ±1.25 lets 2002 in (2019–20 +₹2.7k / DD −₹14.1k) – same
  knife edge as at 300-pt. CAVEATS: ≈3 trades a year, longest idle gap 11 months; in 2019–20 only 1–2 months pass because 400 pts
  was a much wider hedge at NIFTY 9–12k (ratios 30–46%), so those years do not really test the rule. Not adopted.
  USER DECISION 8-Oct-2026: the two-tier rule (thin credit allowed inside ±1%) is DISCARDED – not useful in the current NIFTY regime.
  Do not propose it again. Goal now: lower the 400-pt drawdown and compare with the finalised 300-pt (±2.5% only).
  400-pt drawdown ladder, 2021–26 (n / net / max DD / worst) vs 300-pt final 45 / ₹66,052 / −₹7,527 / −₹7,243: 400 ±2.5% only 44 /
  ₹83,114 / −₹9,814 / −₹9,814; + credit>=42% 36 / ₹75,635 / −₹6,976 / −₹6,976; + credit>=45% 23 / ₹58,379 / −₹4,407; + credit>=46% 19 /
  ₹52,633 / −₹2,989 / −₹1,558; ±2% + credit>=45% 18 / ₹55,772 / −₹1,558; ±2.5% + gap-up exit 44 / ₹88,148 / −₹6,976 (but 2019–20
  −₹11,624 / −₹29,035); ±1.5% only 27 / ₹71,974 / −₹6,976. Credit line is bumpy between 41 and 45%: 41% −₹9,814 (trade 35 at 41.6%
  still in), 42–43% −₹6,976, 44% −₹8,512 (25 tr ₹50,957), 45% −₹4,407. Floor without a >=44% line = trade 67 (43.6%, flat market,
  −₹6,976). 2019–20: 400 ±2.5% −₹4,531 / −₹20,046; + credit>=42% 4 tr +₹9,675 / −₹1,986; >=45% 2 tr +₹3,821; >=46% 1 tr −₹1,986.
  400-pt: credit>=42% vs gap-up exit (8-Oct-2026; user prefers 400-pt ±2.5% + credit>=42% as the comparable alternative to the 300-pt
  final). The −₹9,814 drawdown of 400-pt ±2.5% is trade 35 (stop-loss), NOT trade 67; trade 67 (−₹6,976) is what remains after either
  fix. Both fixes work by removing trade 35 (credit 41.6%; gap-up 1.09% on 15-Nov-23 → −₹1,179), so they are substitutes: 2021–26
  credit>=42% 36 tr ₹75,635 / −₹6,976; gap-up 44 tr ₹88,148 / −₹6,976; both 36 tr ₹74,346 / −₹6,976 (no extra gain). 2019–20: credit>=42%
  4 tr +₹9,675 / −₹1,986; gap-up 15 tr −₹11,624 / −₹29,035. 2019–26: credit>=42% 40 tr ₹85,309 / −₹6,976 / PF 4.35 vs gap-up 59 tr
  ₹76,524 / −₹29,035 vs 400 ±2.5% only ₹78,583 / −₹20,046 vs 300-pt final ₹58,472 / −₹18,795. Caveat: the 42% line is set by trade 35.
  Switching hedge width by credit (user idea, 8-Oct-2026; all inside the ±2.5% filter; r4 = credit / 400-pt width; n / net / max DD;
  2021–26 | 2019–20 | 2019–26). Always 300: 45 ₹66,052 −₹7,527 | 15 −₹7,579 −₹18,795 | 60 ₹58,472 −₹18,795. Always 400 (trade 29 at 300):
  45 ₹85,711 −₹9,814 | 15 −₹4,531 −₹20,046 | 60 ₹81,180 −₹20,046.
  SWITCH 400 if r4>=42% else 300: 45 ₹84,645 −₹7,424 [36×400, 9×300] | 15 −₹3,624 −₹16,459 | 60 ₹81,021 −₹16,459 – 400-pt profit with the
  300-pt drawdown in 2021–26; lines 42–46% all give ₹80–85k / −₹7,424. 400 if r4>=42% else SKIP: 36 ₹75,635 −₹6,976 | 4 +₹9,675 −₹1,986 |
  40 ₹85,309 −₹6,976. THREE-WAY 400 if r4>=45%, 300 if 42–45%, skip below 42%: 36 ₹72,249 −₹5,611 | 4 +₹7,040 | 40 ₹79,288 −₹5,611
  (trade 67 at 300-pt −₹5,523 instead of −₹6,976). The thin months (r4<42%) traded at 300-pt: +₹9.0k in 2021–26 (incl. trade 35
  −₹7,243), −₹13.3k in 2019–20 → they are what brings the −₹16k drawdown back. Why wider-when-rich works: 400 beats 300 by ₹13.8k
  on the 19 months with r4>=46% (worst loss −₹1,558) but only by ₹1.1k on the 8 months below 42% (worst −₹9,814). Reverse rule
  (300 when rich) and switching on the 300-pt ratio or on the 10-day move are worse. Signal must be r4, not r3. Not built in.
  Ideas to add trades/profit to 400-pt ±2.5% & credit>=42% at similar DD (8-Oct-2026; base 2021–26 36 tr ₹75,635 / −₹6,976; 2019–26 40 tr
  ₹85,309 / −₹6,976). (1) Rich credit allowed a bigger 10-day move: only ">=48% at any move" helps (2021–26 40 tr ₹84,536 / −₹6,976;
  2019–26 45 tr ₹102,661) but it is 5 trades and a knife edge – at 47% trade 16 (47.9%, −₹6,074) comes in → DD −₹10,481; with a
  3.5–4% cap DD −₹13k to −₹20k. Not reliable. (2) Rich credit after a FALL only (>=46% & move < −2.5%): +1 trade, +₹2.9k, DD same –
  too few (trade 17). After a RISE: DD −₹16k to −₹20k, never. (3) Profit target 60% instead of 50%: ₹79,261 / −₹6,976 (+₹3.6k, 4
  targets instead of 11); 75% = no target ₹79,389 – small gain, DD unchanged, slower exits. (4) SIZING, not a filter: 2 lots when
  credit>=46%, 1 lot at 42–46%: 2021–26 ₹128,267 / −₹6,976, 2019–26 ₹135,956 / −₹6,976 (worst rich-credit month −₹1,558 per lot;
  at >=45% DD −₹10,488). Doubles margin and the theoretical max loss in those months – user's call. Not tested (need downloads):
  a second index (BANKNIFTY/SENSEX), a second staggered condor per month.
  Profit target on the finalised 300-pt ±2.5% (8-Oct-2026; 2021–26 net, DD −₹7,527 at every level): 50% ₹66,052 (11 targets); 55% ₹67,349
  (7); 60% ₹65,004 (4); 65–75% ₹65,472 (1–0). 60% does NOT help at 300-pt (−₹1,048): four trades gain ₹0.5–1.3k each, but trades 26
  and 60 miss the target and fall back (₹3,476 → ₹1,170; ₹4,183 → ₹1,902). 2019–20 unchanged at every level (no target was hit).
  The target barely matters (range ₹65.0–67.3k); keep 50% for 300-pt. (400-pt + credit>=42%: 60% gave +₹3.6k.)
  400-pt StockMock manual run VALIDATED 9-Oct-2026 (data/reference/IC sell 30delta and 400 points hedge with 50%TP, 100%SL and 18DTE
  exit_StockMock.xlsx; output/reconcile_manual400_vs_backtest.xlsx). File checks all clean: 68 trades × 4 legs, entries 11:16, exits
  15:16, expiries = reference, lot sizes = config.LOT_SIZES, leg P&L adds up, every exit obeys the rules (51 time / 16 target / 1 stop,
  no early or late exit), hedges 400 pts except trade 29 CE 350 (18800/19150). StockMock 68 trades gross ₹79,003, MDD −₹12,235.
  Engine vs StockMock on the 65 common trades: same exit reason 65/65, same exit day 64/65 (trade 31: SM target 7-Aug at 50.1%,
  engine 9-Aug), same strikes 59/65; of those 49 within 3 pts and 56 within 5 pts, credit diff avg −0.04 pts. Gross ₹76,213 (SM) vs
  ₹77,145 (engine); with ±2.5% filter 44 trades ₹93,662 / DD −₹9,720 (SM) vs ₹93,568 / −₹9,540 (engine gross; net ₹83,114 / −₹9,814).
  Strike differences = user's manual picks 50–100 pts from the reference sold strike: 13 (CE 18600 vs 18650), 33 (CE 20400 vs 20300),
  37 (CE 22700 vs 22750), 38 (PE 21300 vs 21350), 45 (CE 26000 vs 26050), 46 (CE 25900 vs 26000). StockMock-only: 24 (−₹2,725, no
  Breeze data), 29 (+₹3,863, engine has no 400/350-pt call hedge price at 11:16), Apr-2026 cycle (entry 16-Mar-26, +₹1,652, 10-day
  move −9.2% → filtered anyway). 400-pt engine results confirmed.
  StockMock 400-pt file revised by the user 9-Oct-2026 ("…_StockMock-2.xlsx", same folder): only two trades changed, both call
  spreads moved to the engine's strikes – trade 37 (15-Jan-24) CE 22700/23100 → 22750/23150, P&L ₹2,936 → ₹2,650 (engine gross
  ₹2,565); trade 46 (14-Oct-24) CE 25900/26300 → 26000/26400, −₹1,547 → −₹1,778 (engine −₹1,661). Overall ₹79,003 → ₹78,486, MDD
  unchanged −₹12,235. Reconciliation with -2: same strikes 61/65; 65 common gross ₹75,696 (SM) vs ₹77,145 (engine); with the ±2.5%
  filter ₹93,376 (SM) vs ₹93,568 (engine). Remaining strike differences: 13, 33, 38, 45.
  400-pt credit>=45% by 10-day limit (9-Oct-2026, 2021–26; n / net / max DD / worst): no 10-day filter 33 / ₹52,542 / −₹14,509 / −₹6,954;
  ±2.5% 23 / ₹58,379 / −₹4,407; ±2% 18 / ₹55,772 / −₹1,558; ±1.5% 13 / ₹44,805 / −₹1,558; ±1% 8 / ₹33,335 / −₹990 (7 winners, 1 loser,
  ₹4,167 per trade; none in 2022 or 2024). Tightening from ±2.5% to ±1% drops 15 trades worth +₹25,044 (4 losers incl. trade 15
  −₹4,407, 11 winners) to save ₹3.4k of drawdown. 2019–20: 2 trades +₹3,821 at ±1% and at ±2.5%. Output: output/hedge400_credit45_trades.xlsx.
  400-pt grid: credit line 40–47% × 10-day limit ±1–3.5% (9-Oct-2026; 2021–26 n / net / max DD, then 2019–26 net / DD). Two stable zones,
  with a worse band between them (43–44%: ₹51–66k, DD −₹7.0k to −₹8.5k):
   ZONE A "more profit" – credit>=42% (41–43) with ±2–2.5%: 31–36 tr, ₹73–76k, DD −₹6,976 (floor = trade 67); 2019–26 ₹83–85k / −₹6,976.
   ZONE B "low drawdown" – credit>=45–46% with ±2–2.5%: 17–23 tr, ₹52–58k, DD −₹1,558 to −₹4,407; 2019–26 ₹50–62k / −₹2.0k to −₹4.4k.
     Best cell: 45% & ±2%: 18 tr ₹55,772 / −₹1,558 (2019–26 ₹59,593 / −₹1,986); 45% & ±2.25%: 21 / ₹58,259 / −₹2,989; 45% & ±2.5%: 23 /
     ₹58,379 / −₹4,407; 46% & ±2.5%: 19 / ₹52,633 / −₹2,989.
   Light option: credit>=40% & ±2.5%: 43 tr ₹82,714 / −₹9,814 (≈ no credit filter in 2021–26) but 2019–26 ₹92,389 / −₹9,814 vs ₹78,583 /
     −₹20,046, because it sits out the 2019–20 months with ratios 30–39%.
   Limits beyond ±3% or below 40% are worse everywhere; ±1–1.5% starves (≤13 trades in zone B). Differences inside a zone are 1–3
   trades (15, 35, 67) – pick the zone, not the cell. Not adopted; engine has no credit filter setting yet.
  What the big 400-pt losers share (9-Oct-2026, 65 trades 2021–26, no filter). Ten worst: 62 −₹11,604, 35 −₹9,814, 8 −₹7,228, 67 −₹6,976,
  19 −₹6,954, 16 −₹6,074, 30 −₹4,991, 52 −₹4,773, 22 −₹4,744, 15 −₹4,407 (7 call side, 3 put side; 5 of them pass ±2.5%: 35, 67,
  30, 22, 15). The ONE common attribute is what NIFTY did AFTER entry: a one-way move of 4–7.7% by the exit (all ten). Size of the
  entry→exit move vs result: |move| < 2% → 33 trades, 0 losers, +₹132.8k; >= 3% → 25 trades, 21 losers, −₹81.8k; >= 5% → 10 trades,
  10 losers, −₹57.1k (correlation with P&L −0.83). Sold strikes sit ≈3% (call) and ≈2% (put) from spot, so a 4–5% move runs
  through the 400-pt spread. Three patterns: (a) rebound rally after a correction, VIX 18–25, NIFTY 6–13% below its high (15, 19,
  22, 52); (b) low-volatility grind to new highs, VIX 11–13 (8, 30, 35); (c) falls – with gap-downs (62, 16) or a slow drift
  with no 1% day (67). NOTHING known at entry separates them sharply: 10-day move (5 of 10 beyond ±2.5%), credit < 45% (7 of 10),
  VIX − realised vol (1.3 vs 2.3 for winners) only tilt the odds – which is what the two filters already use. VIX level, distance
  from the high, 20-day move, strike distance: no difference between losers and winners.
  Early exits / adjustments for losing trades tested 9-Oct-2026 on 400-pt (base ±2.5% 44 tr ₹83,114 / −₹9,814; ±2.5% & credit>=42% 36 tr
  ₹75,635 / −₹6,976), ALL NOT ADOPTED – do not re-test:
  (1) Early loss stop at day N (P&L <= −10/−25/−40% of credit at day 3/5/8/10/12/15): worse in every case (e.g. day 10 & <= −25%:
      5 trades, 2 final losers, exiting costs ₹22.9k). 30 of 65 trades were at −25% at some point; 11 of them ended in profit.
  (2) Early NIFTY-move exit (|move from entry| >= 2/2.5/3% at day 3–12): worse in every case (day 10 & >= 2.5%: 15 trades, only 3
      final losers, exiting costs ₹56k). An early move does not predict the final result.
  (3) Lower or stepped profit target: flat TP 20/25/30/35/40% → ±2.5% ₹58.5k/72.5k/71.0k/70.7k/74.6k, DD unchanged −₹9,814; with
      credit>=42%: TP 25% ₹73,221 / −₹6,192 / worst −₹4,744, win 92%, 14 days held (trade 67 exits at +25% instead of −₹6,976) – costs
      ₹2.4k for ₹0.8k of DD. 300-pt: TP 20–40% ₹45–56k vs ₹66k. "50% then 25% after day 6–10" = same as flat 25%.
  (4) Buy an extra hedge when NIFTY closes beyond the sold strike / mid-spread / hedge strike: −₹53k to −₹84k added over 65 trades
      (helps 62 +₹62.8k, 35 +₹22.7k but 30 of 46 crossings reverse and the extra option decays). Much worse.
  Why reactions fail: breaches usually revert before the exit. Timing of the damage: 7 of the 10 worst trades were flat or in
  profit at day 10 (67 was +28%); the loss came in the last 5–8 trading days. Trades that reached −75% of credit never recovered
  (5 of 5) – only late confirmation. Untested (need downloads): rolling the untested side closer, re-centring the condor,
  two half-size condors entered two weeks apart.
  Direction after a strong 10-day move (10-Oct-2026; NIFTY, every Monday Nov-2018..Sep-2026 = 384 weeks; return over the next 18 trading
  days ≈ the holding period). All weeks: avg +0.7%, up 60%, above −2% in 79%. After a RISE > 2.5% (99 weeks): avg +1.5%, up 68%, above
  −2% in 84%, worst −9.1% → mild continuation, supports a PUT credit spread. After a FALL < −2.5% (46 weeks): avg +1.2%, median
  +3.2%, up 67%, below +3% in only 50%, worst −22.7% → the market usually BOUNCES, so a CALL spread after a fall is the wrong side.
  Splits after a rise (data-mined, treat as hints): VIX not down >10% in 10 days → up 87% / above −2% 92% (52 wks) vs VIX fell >10%
  → up 47% / 74% (47 wks); >4% above 50-DMA → 82% / 93% vs 55% / 75%; rise inside a 60-day downtrend → up 48% / 67%. Size of the rise,
  200-DMA, distance from the high: no use. CAVEAT – the edge has faded: after-rise weeks up 80–86% in 2019–2023 but 50% (2024),
  60% (2025), 14% (2026, 7 weeks). No reliable 20–30 day direction call exists; best statement = "after a rise NIFTY stayed above
  −2% about 5 times in 6". Credit-spread rule (TP/SL etc.) still to be confirmed by the user; not backtested yet.
  Credit spread in filter-skipped months TESTED 10-Oct-2026, NOT adopted (user idea: put spread after a 10-day rise > 2.5%, call spread
  after a fall; same 30Δ sold strike and 300-pt hedge as the IC, entry 11:16, daily 15:16 check, TP 50% of the spread's own credit,
  18-DTE exit; output/credit_spread_skipped_months.xlsx; n / net / max DD). USER RULE, SL 100%: 2021–26 21 tr −₹11,170 / −₹21,171;
  2019–20 8 tr +₹13,157; 2019–26 29 tr +₹1,987 / −₹21,171 (PF 1.05). SL 200%: 2021–26 −₹18,454 / −₹31,885; 2019–26 −₹4,060 / −₹31,885.
  By leg (SL 100%, 2019–26): PUT after a rise 24 tr +₹10,744 / −₹15,040 (17 targets, 6 stops; 2019–20 6 of 6 targets +₹15,783,
  2021–26 18 tr −₹5,039; by entry year 2021–23 +₹3.7k, 2024–26 −₹8.7k); CALL after a fall 5 tr −₹8,757 (wrong side, as the direction
  study said); put after a fall 5 tr +₹1,199; call after a rise 24 tr −₹14,586. SL 100% beats SL 200% everywhere (stops overshoot:
  −₹2.8k to −₹7.0k on ≈₹1.6–2.6k wins). Average credit 65–80 pts on about the same margin as the full IC. Reversal months
  (16, 50, 62, 48, 12, 33) are the losers. Skipping those months remains the better choice.
  Credit spread in skipped months with a 200-pt hedge (10-Oct-2026, 2021–26, 30Δ sold strike, put spread after a rise, 18 trades; net /
  max DD / worst): SL 100% −₹10,311 / −₹13,358 / −₹4,279 (9 targets, 8 stops, credit 46 pts) vs 300-pt −₹5,039 / −₹15,040 / −₹6,155 (11 / 6,
  credit 65); SL 200% −₹10,594 / −₹18,489 vs 300-pt −₹13,069 / −₹26,500. User rule incl. call spread after a fall: 200-pt −₹14.4k (SL 100%)
  / −₹14.3k (SL 200%). Narrower hedge = smaller loss per trade but more stops (trades 1 and 13 flip from target to stop) and smaller
  wins → worse total. PENDING (need the user's Breeze session): 100-pt hedge on the 30Δ strikes (67 calls); 25Δ strikes – strike set
  d25_skip already selected offline (PE avg 143 pts further out, delta 0.249) – candles 173 calls (300-pt) + ≈136 (200) + ≈198 (100);
  20Δ strikes: select_strikes --pe-delta 0.20 --ce-delta 0.20 --around 3 --name d20_skip (3 calls) + candles. Spread simulator is a
  scratch script (not in the repo yet); move it into ic/ if the idea survives.
  Credit spread in skipped months with a 400-pt hedge (10-Oct-2026; 30Δ sold strike; n / net / max DD / worst). PUT spread after a rise,
  SL 100%: 2021–26 18 / −₹3,857 / −₹16,472 / −₹7,542 (11 targets, 6 stops, credit 82 pts); 2019–20 7 / +₹25,817 (7 of 7 targets); 2019–26
  25 / +₹21,960 / −₹16,472 / PF 1.72. SL 200%: 2021–26 −₹14,484 / −₹31,618 / −₹14,923; 2019–26 +₹11,333 / −₹31,618. User rule (plus call
  spread after a fall): SL 100% 2021–26 −₹11,786 / −₹24,401, 2019–26 +₹10,808; SL 200% 2021–26 −₹21,162 / −₹38,296. Width ladder,
  put after a rise, SL 100%, 2021–26: 200-pt −₹10,311; 300-pt −₹5,039; 400-pt −₹3,857 – same 11 winners / 6 losers at 300 and 400,
  wider only scales them. By year (400-pt): 2021 +₹4.7k, 2022 +₹2.7k, 2023 −₹0.2k, 2024 −₹3.7k, 2025 −₹4.6k, 2026 −₹2.8k. No width makes
  2021–26 profitable; the whole 2019–26 gain is 2019–20. Not adopted.
  Up-side limit ladder with PE fixed at 2.5% (net / max DD): no gap exit – 2.5% ₹66,052 / −₹7,527; 3% ₹62,516 /
  −₹8,529; 3.5% ₹56,678 / −₹10,057. With the 1% gap-up exit – 2.5% ₹68,023; 3% ₹68,159; 3.5% ₹67,665, all −₹5,523
  (the gap-up exit rescues trades 62 and 19), but profit factor falls 4.88 → 3.64 → 3.28 and 6–10 more months are traded.
- **What happens after NIFTY crosses a strike** (3-Oct-2026, 300-pt hedges, all 66 trades, NIFTY daily close):
  - CE **hedge** crossed (close ≥ bought call): 7 trades, **all 7 ended in loss** (−₹32.9k; trades 8, 15, 19, 22, 30,
    35, 52). CE **sold** strike crossed: 20 trades, 15 losses / 5 profits.
  - PE sold strike crossed: 28 trades, 20 ended in **profit**; PE hedge crossed: 16 trades, 8 profit / 8 loss –
    falls usually recover, so there is no usable put-side exit point.
  - PE hedge crossed, split by the ±2.5% filter (4-Oct-2026): 9 traded months → 6 profit / 3 loss, +₹1,838 (losers 67
    −₹5,523, 55 −₹2,178, 11 −₹635; 7 of 9 were back above the bought put at exit); 7 skipped months → 2 profit / 5 loss,
    −₹16,500 (62, 16, 48, 50, 46). Losers are the ones still below the bought put on the exit day (7 of 7 lost; of the 9 that recovered above it, 8 made a profit).
  - Exit when NIFTY closes ≥ bought call (call side only), with the ±2.5% filter: ₹66,879 / DD −₹5,997 / worst
    −₹5,523 vs ₹66,052 / −₹7,527 / −₹7,243 – same profit, smaller drawdown (4 exits). Exiting already at the sold
    call costs ≈ ₹12k (trades that recover, e.g. 51, 58). Any put-side exit roughly doubles the drawdown.
  - Built in as an optional rule, off by default (`IC_CE_BREACH_EXIT=hedge`). Combined with the 1% gap-up exit it adds
    nothing: 300-pt with filter – none ₹66,052 / −₹7,527; gap-up ₹68,023 / −₹5,523; call-hedge cross ₹66,898 /
    −₹6,018; both ₹67,989 / −₹5,523. The gap-up exit closes the same rallies (35, 22, 15) earlier, leaving one extra
    exit (trade 30, no gain). With 400-pt hedges the hedge is rarely reached (1 exit, slightly worse: ₹81,190).
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
