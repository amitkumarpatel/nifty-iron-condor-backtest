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
python fetch_index_nse.py --from 2020-08-17 --to 2026-10-09   # NIFTY + India VIX official daily closes from NSE's website (no login)
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
| Sizing | **1 lot** at each expiry's NIFTY lot size (75 until the Jun-2021 expiry → 50 → 25 → 75 → 65, `LOT_SIZES`) |
| Not allowed | Adjustments, re-entry, quantity change, other entry filters |

Order of checks each day: stop-loss → target → time exit.

> **Note – 1% gap-up is an early warning (call side).** In 5 of the 7 trades where NIFTY later closed above
> the bought call – all 7 ended in a loss – NIFTY had first opened ≥ 1% above the previous close, 10 days to
> 3 weeks earlier. Exiting at the 15:16 check on such a gap-up day reduced the max drawdown from −₹7.5k to
> −₹5.5k and raised net profit from ₹66,052 to ₹68,023 (300-pt hedges, ±2.5% filter). The other 2 (trades 30,
> 52) were slow rallies with no 1% gap; there the late warning is NIFTY closing above the bought call.
> The rule is built in but **off by default** (`IC_GAP_UP_EXIT=1.0`); in the forward test it is noted, not acted on.

---

## 1b. Forward-test rule set (400-point condor when credit is rich – switched back from 600 on 18-Oct-2026)

This is the version being paper traded from the October-2026 cycle. It adds a credit test and wider hedges
to the rules of §1. Everything not listed here (Monday 11:16 entry, ~30-delta sold strikes, next-month expiry,
one check a day at 15:16, stop at 100% of credit, time exit at expiry − 18 days, 1 lot, fallback strikes) is
unchanged. Settings: `FWD_*` in `ic/config.py`. `backtest.py` does **not** use them – its defaults stay the
earlier rule below, which is kept as the comparison.

**Two readings.** Evening before entry: NIFTY's 10-day move (NSE official closes). At 11:16: the net credit of
the **400-point** condor (sold ~30-delta call and put, hedges 400 points out). That same condor is the credit
test and, when the credit is rich, the trade.

| 10-day move | Credit of the 400-pt condor | Action | Profit target |
|---|---|---|---|
| within ±2% | 180 points or more (≥ 45% of width) | **400-point condor** | **60%** of credit |
| within ±2% | 160–180 points (40–45%) | **300-point condor** | 50% of credit |
| within ±2% | below 160 points (< 40%) | no condor (floor) → **put credit spread** (below) | 50% of its credit |
| beyond ±2% | any | no condor → **put credit spread** (below) | 50% of its credit |

**Put credit spread in the months the condor rule skips** (added 27-Oct-2026, user's decision; `FWD_PCS_*`):

| Condor skipped and … | Action |
|---|---|
| 10-day move above +2.5% **and** last 5 days +1% or less (rally has stalled) | **Skip the month** |
| anything else (strong rise, 2–2.5% band either way, a fall, thin credit) | **Sell the ~20-delta put, buy the put 200 points lower**; target 50% / stop 100% of its own credit; same entry, 15:16 check and 18-DTE exit |

| 2021–26, 1 lot, net | Put spread trades / net | Won–lost / max DD | Largest possible loss per lot (65) | Condor + put spread |
|---|---|---|---|---|
| **20Δ / 200-pt (chosen)** | 25 / ₹12,114 | 22–3 / −₹1,891 | ≈ ₹11,000 | 61 trades ₹97,843 / DD −₹5,523 |
| 20Δ / 300-pt (shadow log, review in 6–12 months) | 24 / ₹16,346 | 21–3 / −₹2,573 | ≈ ₹16,800 | 60 trades ₹102,075 / DD −₹5,523 |

  300 points earns more only by taking about 50% more risk per trade (profit ÷ largest loss 0.97× vs 1.10×) and
  breaks the 2–3% rule – the same reasoning as 400 vs 600 for the condor, so both widths are reviewed together
  (to switch: `FWD_PCS_WIDTHS = [300]`). The 300-point spread is priced and logged every time. Caveats: 5-day
  filter fitted on these 30 months, only 3 losers, about ₹485 per trade (fills matter); **2019–20 not yet tested
  at 20Δ** (a 30Δ preview lost in that period's thin-credit months). Files: `output/put20_credit_spread_all_skipped_filters.xlsx`,
  `output/combined_ic_plus_put20_spread.xlsx`.

- **A 400-point hedge on rich-credit months** ("variant 3"; user's decision 18-Oct-2026). The 600-point version
  (variant 6, chosen on 12-Oct) earns more in the backtest but its maximum loss, about ₹22,500 a lot, is 4.5–7.5%
  of a ₹3–5L account; the user's limit is 2–3%. 400 points keeps it near ₹13,600 (2.7% of ₹5L). **Review the
  width after 6–12 months of forward testing** (to log both, set `FWD_WIDE_WIDTHS = [400, 600]`).
- **One move limit, ±2%, for all widths** (11-Oct-2026).
- **60% target for the 400-point condor** (50% stays for the 300-point one).
- **Minimum-credit floor:** no condor of any width when the 400-point credit is below 160 points.
- **Backtest, 2021–26** (1 lot, net, NSE official closes; the same 36 months in every row, 17 rich + 19 at 300-pt):

  | Wide condor on rich months | Net P&L | Max drawdown | Worst trade | Win rate | Profit factor | With 0.5-pt slippage | Max possible loss on a rich-month trade (lot 65) |
  |---|---|---|---|---|---|---|---|
  | **400-pt (variant 3, chosen)** | ₹85,729 | −₹5,523 | −₹5,523 | 78% | 5.67 | ₹77,669 | about ₹13,600 |
  | 500-pt (variant 5, not chosen) | ₹100,287 | −₹5,523 | −₹5,523 | 81% | 6.47 | ₹92,227 | about ₹17,900 |
  | 600-pt (variant 6, review later) | ₹114,939 | −₹5,523 | −₹5,523 | 81% | 7.23 | ₹106,879 | about ₹22,500 |

  Earlier rule on the same data: 45 trades ₹66,052 / −₹7,527. Files: `output/six_variant_comparison.xlsx`,
  `output/nifty_hedge_400_500_600_rich_credit_trades.xlsx`.
- **What the table cannot show.** The drawdown is the same in all three rows because it comes from a 300-point
  trade (67). None of the 17 rich-credit months lost more than about ₹2,000, so the backtest never saw a wide
  condor go wrong; the last column is what one such month could cost. 2019–20 has only been run at 400 points
  (4 trades, +₹7,040).

> **Note – the earlier rule is kept as a shadow log.** "300-point condor whenever the 10-day move is within
> ±2.5%" (§1, the `backtest.py` default) was the version first selected for the forward test. Every month,
> also record what it would have done (trade or skip, and the 300-point condor's prices and daily P&L), so the
> two can be compared after a few months.

### Small print behind the final choice

Written for the 400-point version (variant 3); the months, readings and credit lines are the same for the 500 and
600-point versions, only the rupee figures of the 17 rich-credit trades differ. These are the details the backtest numbers above rest on. None changes the rule; each says how much to trust it.

**Months with no result**

- **December 2022 (trade 24) is missing: Breeze has no option data for it.** It would have been a trade: 10-day
  move −0.09%, StockMock credit 177.7 points (44.4% of width) → 300-point condor. StockMock's result for that
  condor is a loss of ₹1,925 before costs. Counting it, 2021–26 is about ₹83.5k, 2022 turns from +₹676 into a
  small losing year (about −₹1.5k), and the drawdown is about −₹5.8k (trades 22 and 24 are back to back).
- **May 2023 (trade 29) has no 400-point credit:** Breeze has no price for the call hedge at 11:16. No effect –
  its 10-day move was +2.23%, so the month is skipped anyway.
- **The April-2026 expiry (entry 16-Mar-2026) is not in the trade list.** No effect – the 10-day move was −9.2%.

**Readings that sit on the ±2% line**

- **The November 2023 stop-loss (trade 35) is skipped by a reading of +2.01%** – 0.01 above the line. Its credit
  was 41.6%, so at 2.00% it would have been a 300-point trade: −₹7,243, total about ₹78.5k, drawdown about −₹7.4k.
- **February 2024 (trade 38) also reads +2.01%.** Harmless: credit 47.9%, the 400-point condor made +₹126.
- **July 2024 (trade 43) reads +2.05%** and is skipped; it made +₹1,937 at 400 points.
- **Just inside:** April 2021 (trade 4, +1.96%, 400-point, +₹2,469) and July 2023 (trade 31, +1.96%, 300-point,
  +₹2,328).
- **The data source decides these.** The readings use NSE's official close (average of the last 30 minutes). With
  Breeze's last-traded close trade 35 read +1.99% and trade 31 +2.11%, and the same rule showed ₹76,284 with a
  −₹9,752 drawdown. The forward test uses NSE's official close, so live decisions follow the same source.

**Credits that sit on the 160-point floor or the 180-point line**

- **June 2023 (trade 30) is in by 0.2 of a point:** credit 160.2 points (40.05%). It is the second-largest loss
  (−₹3,731, 300-point).
- **July 2023 (trade 31)** is in at 162 points (40.5%), +₹2,328.
- **September 2024 (trade 45) is out at 158.6 points (39.6%)**, a +₹859 winner. Its call-hedge price at 11:16
  looks like a bad print, which lowered the credit.
- **May 2025 (trade 53) is the closest 400-point trade:** 45.7%, +₹3,645 (+₹2,400 at 300 points).
- **Trades 22 (44.4%) and 55 (44.5%) fall just under 45%**, so they run at 300 points. Both lost, and the
  narrower hedge made the losses smaller (−₹3,654 instead of −₹4,744; −₹2,178 instead of −₹2,678).
- **In 2019–20 the floor does most of the work:** only 4 of 23 months pass, because 400 points was a much wider
  hedge when NIFTY was at 9,000–12,000 (credit 30–39% of width). Those years barely test the rule.

**What widening the 300-point limit from ±1.5% to ±2% changed**

- Six more trades, +₹4,382 in total: winners 51 (+₹3,900), 58 (+₹3,077), 31 (+₹2,328), 40 (+₹908); losers 22
  (−₹3,654) and 55 (−₹2,178). Same drawdown and same worst trade.
- Profit factor falls from 7.49 to 5.67 and the win rate from 80% to 78%.

**What the rule does not fix**

- **The worst trade, August 2026 (trade 67, −₹5,523), passes every test:** move −0.07%, credit 43.6%, flat market
  at entry. Nothing known at entry separates it. It is the drawdown.
- **Thresholds were chosen on this data.** Four numbers (2%, 45%, 40%, 60% target) and about six trades a year.
  Treat the backtest as an upper bound and expect less live.
- **Costs are approximate (about ₹250 per condor) and there is no slippage** in the figures. With 0.5 point per
  leg: ₹77,669; with 1 point: ₹69,609.
- **The 400-point condor needs more margin and has a bigger maximum loss** (about 219 points against 154).
- **The engine has no setting for this rule.** The figures combine the no-filter 300-point and 400-point runs.

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
| "Option C" (first version, 10-Oct-2026): 400-pt when 10-day move ≤ ±2% and credit ≥ 45% of width, else 300-pt when move ≤ ±1.5%, else skip | **Superseded 11-Oct-2026 by §1b (one ±2% limit for both widths, 160-pt floor).** Figures on Breeze closes: 2021–26: 32 trades ₹78.9k / DD −₹5.5k vs current ₹66.1k / −₹7.5k; 2019–26 ₹78.7k / −₹13.0k vs ₹58.5k / −₹18.8k. Three thresholds fitted on this data |
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
│   ├── nifty_daily.csv     # NOT committed: NIFTY daily OHLC, NSE official closes (trend filter) – fetch_index_nse.py
│   ├── india_vix_daily.csv # NOT committed: India VIX daily OHLC from NSE – fetch_index_nse.py
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
| `python download.py --index` | NIFTY and India VIX daily prices from Breeze – only fills days the files lack; the official closes come from `fetch_index_nse.py` (§5.3a) | Yes (a few calls) | `data/nifty_daily.csv`, `data/india_vix_daily.csv` |
| `python download.py [--trades ...]` | 1-minute candles for every leg, plus fallback strikes; restart-safe | Yes (~3,500 calls first time) | `data/cache/` |
| `python backtest.py` | Replays all trades with the current rules | No | `output/IC_backtest_report.xlsx` |
| `python backtest.py --trades 1 9 23 --out output/x.xlsx` | Selected trades / separate report file | No | the `--out` file |
| `python export_prices.py [--trades ...] [--out file]` | Daily price of every leg of every trade, entry to exit (11:16 entry, 15:16 checks, day OHLC), incl. filter-skipped months | No | `output/IC_leg_prices.xlsx` |
| `python fetch_index_nse.py --from 2026-09-01 --to 2026-10-09 [--replace]` | **Source of the NIFTY close used by the filter:** NSE's official daily closes for NIFTY and India VIX, merged into the daily files and the calendar (`--replace` overwrites days already there) | No (NSE website) | `data/nifty_daily.csv`, `data/india_vix_daily.csv` |
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
| `IC_EXIT_DTE` | `18` | time exit N calendar days before expiry (same as `--exit-dte N`) |
| `IC_TP` | `50` | profit target in % of credit, e.g. `40` (same as `--tp 40`) |
| `IC_INDEX` | `NIFTY` | index to work on: `NIFTY` or `BANKNIFTY` (same as `--symbol banknifty`); see §5.3e |
| `IC_DATA_DIR`, `IC_OUTPUT_DIR`, `IC_REF_DIR` | `data/`, `output/`, `data/reference/` | alternative folders (used by the smoke test) |
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
- Run `python fetch_index_nse.py` as well (section 5.3a) – the backtest needs NIFTY's official daily
  closes for the trend filter.
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
The filter uses **NSE's official closes** (the last-30-minute average NSE publishes as the day's close):
```bash
python fetch_index_nse.py --from 2026-09-01 --to 2026-10-09 --replace    # NSE website, no login
```
`python download.py --index` (Breeze) only fills days the file does not have yet. Breeze's daily "close" is
the last traded index value, which differed from the official close by about 6 points on average and up to
245 points on single days in 2020–2024 (identical from 2025). Since 11-Oct-2026 the whole file holds NSE's
official values, the same source the forward-test skill reads, so backtest and live readings agree.
**Where each NIFTY number comes from**

| Number | Used for | Source | When it is available |
|---|---|---|---|
| NIFTY daily close (official) | 10-day move in the backtest (`data/nifty_daily.csv`) | NSE daily index file `archives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv`, row "Nifty 50", column "Closing Index Value" – `fetch_index_nse.py` | Evening of each trading day |
| NIFTY daily close (official) | 10-day move in the forward test (`ic_tools.py filter`, `strikes`), previous close for the gap-up log (`check`) | The same NSE file, read live for the last 11 sessions | Evening of each trading day |
| NIFTY daily open | Gap-up reading in the backtest | Same NSE file, "Open Index Value" | Same |
| India VIX daily | Studies only (not in the rules) | Same NSE file, row "India VIX" | Same |
| NIFTY spot at 11:16 | Delta of the strikes in `select_strikes.py` | Breeze 1-minute candles | Needs a Breeze session |
| Option prices at 11:16 / 15:16 | Every trade's entry, daily check and exit in the backtest | Breeze 1-minute candles | Needs a Breeze session |
| Live option chain | `ic_tools.py strikes` in the forward test | NSE website option chain (lags a few minutes) | Market hours |

- The official close is NSE's average over the last 30 minutes of the session; it is the figure quoted as "the close".
  It is **not** the last traded value, which is what Breeze's daily candle gives.
- The 10-day move for an entry day uses the official close of the previous trading day and the official close 10
  trading days before that. Special sessions (Diwali Muhurat, a Budget-day Saturday/Sunday) count as trading days.
- If NSE's site cannot be reached, the forward-test `filter` falls back to `data/nifty_daily.csv` and prints a warning.

The older Breeze command, kept for the days NSE's site cannot be reached:
```bash
python download.py --index
```
A handful of API calls. Adds any days missing from `data/nifty_daily.csv` and `data/india_vix_daily.csv`
(`config.INDEX_DAILY`); it never overwrites a day that is already there. To extend the files before
backtesting new months, use `fetch_index_nse.py` so the new days carry the official close.

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
- `--entry-weeks N` enters on the Monday N weeks before the expiry week (default 6 = 43–45 DTE; 7 = 50–52 DTE);
  `--entry-dte N` enters exactly N calendar days before expiry. Example (entry one week earlier, exit at 25 DTE, 40% target):
  `make_trades.py --from 2021-01 --to 2026-08 --entry-weeks 7 --name w7`, then `select_strikes.py --trade-set w7 ...`,
  `download.py --trade-set w7 --strike-set d30_w7 --hedge 400 --exit-dte 25` and `backtest.py ... --exit-dte 25 --tp 40`.
- `fetch_index_nse.py` only adds days that are missing (use `--replace` to overwrite) and also extends the
  trading calendar. `download.py --index` now merges too, so it no longer drops earlier history.
- Lot size for expiries up to Jun-2021 is 75 (`LOT_SIZES`; NSE circular FAOP47854).

### 5.3e Another index: BANKNIFTY (added 11-Oct-2026)

The same engine and the same rules run on a second index. Add `--symbol banknifty` to any script (or set
`IC_INDEX=BANKNIFTY`). Without it everything works on NIFTY exactly as before – the NIFTY reports were compared
before and after the change and are identical.

**What is separate per index** (table `INDEXES` in `ic/config.py`):

| Item | NIFTY | BANKNIFTY |
|---|---|---|
| Breeze stock code | `NIFTY` | `CNXBAN` (confirmed by the probe, 11-Oct-2026) |
| Strike spacing | 50 | 100 |
| Default hedge width | 300 | 500 (the StockMock BANKNIFTY run) |
| Fallback strike shifts | −50, +50, −100, +100; hedge +50, +100 | −100, +100, −200, +200; hedge +100, +200 |
| Lot size by expiry | as before | 25 → 15 (from the Jul-2023 expiry) → 30 (Feb-2025) → 35 (Jul-2025) → 30 (Jan-2026) |
| Monthly expiry day (`make_trades.py` only) | Thursday, Tuesday from Sep-2025 | Thursday; Wednesday Mar–Dec 2024; Thursday; Tuesday from Sep-2025 (matches the report) |
| Reference trades | `data/reference/ic_reference_trades.csv`, `ic_reference_legs.csv` | `data/reference/banknifty_ic_reference_trades.csv`, `banknifty_ic_reference_legs.csv` |
| Generated trade sets | `ic_trades_<name>.csv` | `banknifty_ic_trades_<name>.csv` |
| Strike sets | `data/strike_sets/strikes_<name>.csv` | `data/strike_sets/banknifty/strikes_<name>.csv` |
| Candle cache | `data/cache/NIFTY_<expiry>_<strike>` | `data/cache/BANKNIFTY_<expiry>_<strike>` |
| Daily closes for the 10-day filter | `data/nifty_daily.csv` | `data/banknifty_daily.csv` (BANKNIFTY's own move) |
| Reports | `output/IC_backtest_report.xlsx` | `output/BANKNIFTY_IC_backtest_report.xlsx` (variants: `BANKNIFTY_IC_backtest_<set>_h<width>…`) |

**What is shared:** entry 11:16, one check at 15:16, stop 100% / target 50% of credit, 18-DTE time exit, the ±2.5%
10-day filter (measured on BANKNIFTY's own closes), the trading-day calendar, the Muhurat days and the cost model.
The forward-test rule set of §1b (`FWD_*`) and the Claude skill are NIFTY only.

```bash
python fetch_index_nse.py --from 2018-10-01 --to 2026-10-09      # official closes: NIFTY, India VIX and BANKNIFTY (no login)
python probe.py --symbol banknifty --trades 1 2 3                # API: does Breeze have the option data? (needs the reference files)
python download.py --symbol banknifty --dry-run                  # count the calls first
python download.py --symbol banknifty                            # API
python backtest.py --symbol banknifty                            # offline -> output/BANKNIFTY_IC_backtest_report.xlsx
python backtest.py --symbol banknifty --hedge 900 --filter off   # variants work the same way
# without a StockMock report: generated trades + delta-picked strikes, as in section 5.3d
python make_trades.py --symbol banknifty --from 2021-01 --to 2026-08 --name bn
python select_strikes.py --symbol banknifty --trade-set bn --ce-delta 0.30 --pe-delta 0.30 --around 4 --name d30_bn
```

**StockMock BANKNIFTY report** (`data/reference/Banknifty IC backtesting_StockMock.xlsx`, validated 11-Oct-2026;
the two `banknifty_ic_reference_*.csv` files are built from it):

- 67 trades × 4 legs, the same 67 months as the NIFTY reference; entries 11:16, exits 15:16; leg P&L adds up to
  every trade's P&L. Overall ₹25,894 before costs, largest loss −₹10,836 (trade 62), 41 winners / 26 losers.
- Rules: ~30-delta sold strikes, hedges 500 points out, target 50%, time exit at 18 DTE. 58 time exits, 5 targets
  (6, 29, 39, 49, 54), 1 trade beyond −100% on the time-exit day (62, −154% of credit).
- Entry dates equal NIFTY's except trade 42 (18-Jun-2024 instead of 10-Jun: BANKNIFTY's expiry was Wed 31-Jul).
- **Three exits are one trading day before the 18-DTE day** – trades 24 (5-Jan-2023), 41 (6-Jun-2024), 42
  (11-Jul-2024). Marked `MANUAL`, so the engine's different exit day is an expected mismatch.
- **Two trades have hedges wider than 500 points** – 58 (call 600) and 61 (call and put 600). The engine moves
  them to 500 (fallback rule if a strike has no price).
- **Lot size differs for two trades** – StockMock used 25 for the Jul-2023 and Aug-2023 expiries (trades 30, 31);
  NSE's circular made it 15 from the July-2023 expiry. The engine uses 15; at those lots the StockMock total is
  ₹24,690.
- No trade for the April-2026 expiry, as in the NIFTY reference.

Probe 11-Oct-2026 (8 trades, 64 checks): Breeze returned data for all 64, every year 2021–2026; the engine's price
rule (exact minute, else last traded price) is within 2% of StockMock on 59 of 64. 13 checks had no candle at the
exact minute – BANKNIFTY monthly options six weeks out trade thinly in 2021–22 (trade 9: sold call last traded 41
minutes before 11:16).

**First BANKNIFTY backtest (11-Oct-2026; data downloaded, 0 trades without data;
`output/BANKNIFTY_IC_backtest_report.xlsx`, no-filter run `BANKNIFTY_IC_backtest_sm_h500_nofilter.xlsx`).**
Same rules as NIFTY: 30-delta, 500-point hedges, target 50%, stop 100%, 18-DTE exit, 1 lot.

| | Trades | Gross | Net of costs | Max drawdown (net) | Worst trade (net) | Win rate | Profit factor (net) |
|---|---|---|---|---|---|---|---|
| No filter | 67 | ₹26,060 | ₹8,291 | −₹12,043 | −₹8,866 | 57% | 1.13 |
| ±2.5% 10-day filter (BANKNIFTY's own move) | 37 | ₹21,185 | ₹11,709 | −₹12,256 | −₹5,024 | 57% | 1.39 |
| ±2% | 28 | ₹28,456 | ₹21,373 | −₹9,774 | −₹5,024 | 64% | 2.15 |
| ±1.5% | 20 | ₹31,131 | ₹26,124 | −₹6,439 | −₹5,024 | 80% | 3.84 |
| ±3% | 46 | ₹16,760 | ₹4,806 | −₹15,892 | −₹5,024 | 52% | 1.12 |

- **Engine vs StockMock (67 trades, no filter):** gross ₹26,060 against ₹24,690; 36 trades within 3 points, 55 within
  10, 60 within 20; same exit day and reason on 61. Differences: the three manual exits (24, 41, 42), trade 61
  (StockMock's hedges were 600 points), and the two stop-losses below.
- **Costs take most of the profit:** about ₹265 per condor against an average gross profit of ₹389 – ₹17,769 of
  the ₹26,060. BANKNIFTY's lot is small (15–35) while premiums are large, so the rupee profit per trade is small.
- **The stop and the target hardly ever act.** The credit averages 262 points = 52% of the 500-point width, so the
  largest possible loss (238 points) is about 93% of the credit: a stop at 100% of credit cannot be reached in 45
  of 67 trades. Only 6 trades reached the 50% target. Nearly every trade is a time exit.
- **Both engine stop-losses are bad prints, not real stops.** Trade 37 (29-Jan-2024) and trade 62 (9-Mar-2026)
  show the condor worth 557 and 517 points – more than the 500-point width, which is impossible. Deep
  in-the-money puts trade rarely and the two legs' last prices are from different moments. StockMock's own −361
  points for trade 62 is beyond the maximum loss for the same reason. With trade 37 held to its time exit as in
  StockMock: no filter ₹11,423 net; ±2.5% ₹14,841 net, drawdown −₹9,124. The NIFTY runs have no such day.
- **The filter skips far more months than on NIFTY** (30 of 67 at ±2.5%, against 21) because BANKNIFTY moves more.
  Tighter limits look better (±1.5%: 20 trades), but that is three or four trades a year, chosen after seeing the data.
- **Thin data in 2021–22:** 432 of the 487 non-exact prices are in those two years (83 older than 15 minutes).
- Compared with NIFTY on the same months (300-point, ±2.5%: ₹66,052 net, drawdown −₹7,527), BANKNIFTY with these
  rules earns about a fifth for a larger drawdown.
- **1,000-point hedges (12-Oct-2026) – the wider hedge does lift profit.** n / gross / net / net DD /
  worst / PF): data usable – 62 of 67 ran (2, 4, 24, 57, 66 no hedge price), 9 on fallback strikes, 0 days with value > width, credit 1.76× the
  500-pt credit (2 odd: 40 at 1.13×, 64 at 2.28×). No filter 62 / ₹48,358 / ₹32,471 / −₹18,505 / −₹14,421 (trade 62) / 1.35; ±3% 42 / ₹23,237 net /
  −₹21,610; ±2.5% 34 / ₹44,008 / ₹35,593 / −₹13,944 / −₹7,025 / 1.93; ±2% 26 / ₹51,983 / ₹45,623 / −₹10,171 / −₹6,746 / 2.86; ±1.5% 19 / ₹52,204 net /
  −₹3,993 / PF 7.10. Same 62 trades at 500-pt: ₹5,928 net → the wider hedge DOES lift profit (user's idea confirmed; 1,000 better on 42 of 62).
  Why: credit 457 pts = 46% of width (500-pt: 52%), so stop and target work again – 8 targets, 3 real stops at −105% (35, 48, 62);
  costs ≈ ₹256/condor are now 33% of gross instead of 68%. Cost of it: losses double (62 −₹8.9k → −₹14.4k; 48, 19, 35, 51, 16 each −₹3.5k →
  ≈ −₹7k), max loss/condor 543 pts ≈ ₹16.3k at lot 30. By year ±2.5%: 2021 +8.6k, 2022 −8.8k, 2023 +14.1k, 2024 +3.2k, 2025 +10.8k, 2026 +7.7k.
  0.5-pt slip ±2.5% ₹32,473. Versus NIFTY 300-pt ±2.5% (₹66,052 / −₹7,527): about half the profit with nearly twice the drawdown; 174+170
  of the 418 non-exact prices are 2021–22. ±1.5%/±2% look best but were picked after seeing the data (3–4 trades a year). Not adopted.
- **Not an alternative for NIFTY's skipped months (12-Oct-2026).** The two filters pick mostly the same months: 10-day
  moves correlate 0.81; at ±2.5% NIFTY passes 45 of 67, BANKNIFTY 36, both 32, NIFTY only 13, BANKNIFTY only 4 (23, 24, 33, 52), neither 17
  (at ±2%: 37 / 27 / both 21 / NIFTY only 16 / BANKNIFTY only 6). The 3 BANKNIFTY-only months with data made −₹3,483 at 1,000-pt (52 −₹3,401).
  Months the finalised NIFTY rule skips but BANKNIFTY ±2.5% passes: 11 tr −₹2,212. Trade P&L correlation NIFTY 300-pt vs BANKNIFTY 1,000-pt
  0.61 (62 months, no filter); both lose in 15 of NIFTY's 24 losing months; 7 of NIFTY's 10 worst months lose on BANKNIFTY too (62, 35, 19,
  16, 52, 22, 15); exceptions 67, 8, 30. Running both (each with its own ±2.5% filter): ₹101,644 / DD −₹17,607 (NIFTY ₹66,052 / −₹7,527 +
  BANKNIFTY ₹35,593 / −₹13,944); finalised NIFTY rule (400-pt) + BANKNIFTY ₹121,321 / −₹11,126. BANKNIFTY adds size, not diversification.
- **600-point hedges cannot be tested reliably (12-Oct-2026).** the hedge strikes do not trade.
  Far BANKNIFTY strikes six weeks out trade on round 500s; 75% of the sold strikes are on a round 500, so a 600-pt hedge lands on an odd
  hundred (e.g. 34600). Result: 23 of 67 trades had no hedge price at entry and did not run, 17 of the 44 that ran used fallback strikes,
  699 non-exact prices (244 stale > 15 min), and 14 of the 44 show an impossible credit (a wider hedge must collect more than the 500-pt
  condor: 8 collect less, 6 collect 1.5–2.5× as much, e.g. trade 41 credit 637 pts on a 600-pt width). Headline (unreliable): 44 tr net
  −₹8,791 / DD −₹23,334 no filter; ±2.5% 25 tr −₹3,317; the same 44 trades at 500-pt −₹8,159. Only 19 trades are clean (plausible credit, no
  fallback): 600-pt −₹21,355 vs 500-pt −₹19,246, 600 better on 8 – no sign that the wider hedge helps. Do NOT download 700-pt (same odd-strike
  problem). The testable wider hedge is 1,000 pts (lands on round 500s like the 500-pt run, which had 0 trades not run and 1 fallback).

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
**Forward-test plan (400-point wide condor from 18-Oct-2026):** 1 lot for 3–6 months with the rule set
of §1b – Monday ~11:15–11:16 entry (~43 DTE), ~30Δ CE + PE sold; trade only when the 10-day move is within ±2%:
a 400-point condor (60% target) when its credit is at least 180 points, a 300-point condor (50% target) when that credit is 160–180 points, no condor below 160 points; stop at
−100% of credit, time exit at 18 DTE. In every month without a condor: a 20-delta put credit spread with a 200-point
hedge (50% target, 100% stop of its own credit), except after a 10-day rise above 2.5% whose last 5 days added
+1% or less (skip); the 300-point put spread is shadow-logged.
Every month also log what the earlier rule (300-point, ±2.5%) would have done, and note (not act on) the
condor's 15:16 P&L on every 1% gap-up day.

The project only reads historical data – it never places orders. Each month:

1. **Evening before the planned entry (43 DTE, the Monday six weeks before the Tuesday expiry):** check
   NIFTY's 10-day move (last close vs the close 10 trading days earlier) against the forward-test rule of §1b:
   within ±2% → trade (the 400-point credit at entry decides the width, or no condor below 160 points); beyond ±2% → no
   condor. With no condor, `filter` also prints the put credit spread verdict (5-day move check).
   `python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py plan --expiry YYYY-MM-DD` gives the entry and
   time-exit dates, `... ic_tools.py filter --entry-date YYYY-MM-DD --show` gives the reading from NSE's website
   (no Breeze login), with the verdict of both the forward-test rule and the earlier ±2.5% rule.
   NSE holidays for the entry/exit dates are kept in `NSE_HOLIDAYS` (`ic/config.py`); refresh them each
   January with `... ic_tools.py holidays --write`. Monthly expiries move to the previous trading day when the
   Tuesday is a holiday (Nov-2026 expiry = Mon 23-Nov).
2. **Entry at 11:16:** price the 400-point condor first (sell the ~30-delta CE and PE, hedges 400 points
   further out); its credit decides between the 400-point condor, the 300-point condor and no trade (§1b).
   `... ic_tools.py strikes --expiry YYYY-MM-DD` reads NSE's option chain, prices the 400-point and the
   300-point condor, applies the §1b table (credit of the 400-point condor against 180 / 160 points) and prints
   the decision, the legs with bid/ask, the credit, the target (60% or 50%), the stop and the maximum loss, plus
   what the earlier rule would do; when the condor is skipped it also prices the 20-delta put spread (200-point
   chosen, 300-point shadow) (NSE's chain lags a few minutes – confirm prices in the broker terminal). If a
   strike has no price, use the fallback rule (spread 50/100 points closer or further, else a
   350/400-point hedge).
3. **Every day at 15:16:** exit all 4 legs at −100% of the credit (stop) or at the target – +60% for a
   400-point condor, +50% for a 300-point one.
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
| "What are the current rules?" | Prints the forward-test rule set (§1b) and the live values from `ic/config.py` | `rules` |
| "Plan the November cycle" | Gives one entry date (the Monday six weeks before expiry) and the time-exit date, using the NSE holiday list in config; prints a note when the expiry is not a Tuesday and a warning when a year has no holiday list | `plan --expiry` |
| "Should I enter this month?" | Reads the last 11 NIFTY closes from NSE's website and reports the 10-day move with the forward-test verdict (trade / trade only if credit is rich / skip) and the earlier ±2.5% rule's verdict; uses `data/nifty_daily.csv` only if NSE is unreachable | `filter --entry-date` |
| "Refresh the NSE holidays" | Shows NSE's F&O holiday list and what would change; with your agreement, writes it into `NSE_HOLIDAYS` in `ic/config.py` | `holidays [--write]` |
| "Which strikes for this expiry?" | Reads NSE's option chain, finds the strikes nearest 30 delta, prices the 400-point and 300-point condors (with the fallback rule), decides the width from the 400-point credit and the 10-day move, and prints bid/ask, credit, target, stop and maximum loss | `strikes --expiry` |
| "Log today's check" | Takes the four 15:16 leg prices and reports HOLD, TARGET, STOPLOSS, TIME or GAP_UP, with a 60% target for a 400-point condor and 50% for a 300-point one; fetches the previous close from NSE if it is not given; logs to `journal/forward_daily.csv` | `check --log` |
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
  USER PLAN 10-Oct-2026: deploy the 400-pt IC when |10d move| <= 2% AND credit >= 45% of the 400-pt width; otherwise a 300-pt IC under a
  filter still to be chosen. Options for the 300-pt part (n (400/300) / net / max DD; 2021–26 | 2019–20 | 2019–26; r4 = 400-pt credit
  ratio, r3 = 300-pt ratio): 400 rule only, rest skipped: 18 ₹55,772 −₹1,558 | 2 +₹3,821 | 20 ₹59,593 −₹1,986.
   + 300 on the rest inside ±2.5%: 45 (18/27) ₹80,784 −₹7,424 | 15 −₹6,258 −₹19,093 | 60 ₹74,525 −₹19,093 (3 losing years).
   + 300 on the rest inside ±2.5% & r4>=42%: 36 (18/18) ₹71,774 −₹5,523 | 4 +₹7,040 −₹1,986 | 40 ₹78,814 −₹5,523 (PF 4.71) ← best balance.
   + 300 inside ±2.5% & r4>=40%: 43 ₹77,329 −₹7,424 | 4 +₹7,040 | 47 ₹84,369 −₹7,424.   + 300 inside ±2%: 38 ₹73,727 −₹9,752 | 2019–26 −₹18,196 DD.
   + 300 inside ±2.5% & r3>=48%: 27 (18/9) ₹57,403 −₹3,820 | 3 +₹5,122 | 30 ₹62,525 −₹3,820.   r3>=45/46%: ₹61–63k / −₹9,752 (worse).
   + 300 inside ±1.5%: 32 ₹78,916 −₹5,523 | 9 −₹194 −₹12,988 | 41 ₹78,721 −₹12,988.
  The 27 "remaining" ±2.5% months at 300-pt made +₹25,012 in 2021–26 (19 winners; losers 35 −₹7,243, 67 −₹5,523, 30, 22, 15, 55, 41, 11).
  300-pt alone for reference: ±2.5% 45 ₹66,052 −₹7,527 | 2019–26 ₹58,472 −₹18,795; ±2.5% & r3>=48% 26 ₹40,271 −₹4,003 | 2019–26 ₹44,072 −₹4,003.
  Awaiting the user's choice; nothing built into the engine yet.
  OPTION C vs the current forward-test rule (10-Oct-2026; user prefers C on 2021–26, not yet adopted/built). C = 400-pt IC if |10d move|
  <= 2% and credit >= 45% of the 400-pt width; else 300-pt IC if |10d move| <= 1.5%; else skip. Current = 300-pt IC if |10d| <= 2.5%.
  2021–26: current 45 tr ₹66,052 / DD −₹7,527 / worst −₹7,243 / win 73% / PF 3.20 / 1 losing year / 0.5-pt slip ₹56,492;
  C 32 tr (18×400 + 14×300) ₹78,916 / −₹5,523 / −₹5,523 / 81% / 7.30 / 0 losing years / slip ₹72,056. Where the +₹12,864 comes from: 18
  trades moved to 400-pt +₹14,732 (16 of 18 better); 13 trades dropped (10-day move 1.5–2.5% without rich credit) made +₹1,866 in
  total = 5 losers −₹17.7k (35, 22, 15, 55, 41) and 8 winners +₹19.6k; 14 trades unchanged. 2019–20: current −₹7,579 / −₹18,795; C 9 tr
  −₹194 / −₹12,988 (still takes the Feb-2020 stop −₹11,002: move −1.22%). 2019–26: current 60 tr ₹58,472 / −₹18,795 / PF 1.95; C 41 tr
  ₹78,721 / −₹12,988 / PF 3.80. Caveats: 3 thresholds chosen on this data; trade 67 (−₹5,523) is in both; ≈5 trades a year.
  Option C tweaks tested 10-Oct-2026 (n / net / max DD; 2021–26 | 2019–26). Base C: 32 ₹78,916 −₹5,523 | 41 ₹78,721 −₹12,988.
  STABILITY: 400-pt move limit 1.75/2/2.25/2.5% with credit 45–46% and 300-pt limit 1.25–1.75% all give ₹70–89k / −₹5,523; the only
  cliff is a 300-pt limit of ±2% (−₹9,752: lets in 22 and 55). 300-pt limit 1.25 ₹71.3k, 1.5 ₹78.9k, 1.75 ₹86.8k (adds 51, 58, 40) –
  1.5 sits mid-plateau; keep it. Credit 44% adds a losing year (trade 22).
  SIMPLER FORMS: one move limit ±1.5% for both widths 27 ₹67,950 −₹5,523 (−₹11k: drops rich-credit trades at 1.5–2%); one limit ±2%
  ₹73,727 −₹9,752; same months all at 400-pt 32 ₹82,940 −₹6,976 | ₹85,600 −₹14,068; all at 300-pt ₹64,184 −₹5,523.
  SAFETY FLOOR (best tweak): no 300-pt trade when the 400-pt credit is below 40% of width (160 pts): 2021–26 31 ₹78,057 −₹5,523
  (only trade 45 drops) but 2019–20 becomes 4 tr +₹7,040 (Feb-2020 stop had 35.4%) → 2019–26 35 ₹85,097 −₹5,523, no losing year.
  Floors 38–41% all similar; 42% cuts 2021–26 to ₹70,664. TP 60% on the 400-pt trades only: ₹82,331 −₹5,523 (+₹3.4k); on both ₹79,532.
  EASY FORM (same trades as C + floor), credit in points of the 400-pt condor: move <= 1.5%: >= 180 pts → 400-pt; 160–180 → 300-pt;
  < 160 → skip. Move 1.5–2%: >= 180 pts → 400-pt, else skip. Move > 2%: skip. Not adopted/built yet – user to confirm.
  DATA-SOURCE FINDING 11-Oct-2026 (user cross-check): data/nifty_daily.csv from Breeze (download.py --index, 1-day candles) is NOT NSE's
  official close – Breeze's daily close is the last traded index value, NSE's official close is the last-30-minute average.
  On the 134 dates behind the 67 filter readings: average gap 5.7 pts, max 40 pts (e.g. 10-Nov-2023 19,443.45 vs 19,425.35; 13-Nov-2023
  19,440.15 vs 19,443.55). 10-day move differs by 0.04 pts on average, max 0.24. Decisions that flip with NSE official closes:
  ±2.5% none (earlier rule and main report unchanged, 45 tr ₹66,052); ±2% three – trade 31 (2.11 → 1.96), 35 (1.99 → 2.01), 38 (1.94 → 2.01);
  ±1.5% one – trade 14 (1.41 → 1.60). Adopted forward-test rule (TP 50% basis): Breeze 31 tr ₹78,057 / −₹5,523; NSE 30 tr ₹77,931 /
  −₹5,523 (only trade 38 drops, +₹126). "±2% for both widths, credit 40–45% at 300-pt" variant: Breeze 37 tr ₹72,869 / −₹9,752; NSE
  36 tr ₹82,313 / −₹5,523 – because trade 35 (stop-loss) reads 2.01% and is skipped. So that variant's verdict hangs on 0.02 pts of
  one reading; do not treat ±2% vs ±1.5% for the 300-pt leg as settled. The forward-test skill already uses NSE official closes
  (live readings follow NSE, not Breeze). 2019–Aug-2020 rows in nifty_daily.csv are already NSE. TO DECIDE with the user: replace
  the Breeze rows by NSE official closes (python fetch_index_nse.py --from 2020-08-17 --to <today> --replace; ~1,500 small files,
  no Breeze login) so backtest and forward test use the same source.
  FINAL FOUR-WAY COMPARISON on NSE official closes (11-Oct-2026; output/final_variant_comparison.xlsx; 1 lot, net; 400-pt trades with the
  60% target; n / net / max DD / worst / PF). 2021–26: no filter (300-pt) 66 / ₹47,298 / −₹11,860 / −₹8,529 / 1.67; ±2.5% (300-pt) 45 /
  ₹66,052 / −₹7,527 / −₹7,243 / 3.20; "±2% both" (400-pt if credit>=45%, 300-pt if 40–45%) 36 (17+19) / ₹85,729 / −₹5,523 / −₹5,523 / 5.67;
  ADOPTED (400-pt ±2% & >=45%, 300-pt ±1.5% & >=40%) 30 (17+13) / ₹81,346 / −₹5,523 / −₹5,523 / 7.49. 2019–20: −₹34,106 / −₹40,887; −₹7,579 /
  −₹18,795; both credit rules 4 tr +₹7,040 / −₹1,986. 2019–26: 89 / ₹13,192 / −₹42,721; 60 / ₹58,472 / −₹18,795; 40 / ₹92,768 / −₹5,523 (PF 5.56);
  34 / ₹88,386 / −₹5,523 (PF 7.09). The two credit rules differ by 6 trades with a 1.5–2% move: 51 +₹3,900, 58 +₹3,077, 31 +₹2,328,
  40 +₹908, 22 −₹3,654, 55 −₹2,178 = +₹4,382. Trade 35 (2.01%) is out of both by 0.01.
  GAP-UP vs THE BIG LOSERS, re-checked for the variant-6 rule (12-Oct-2026, user observation "Nov-2023 and Feb-2026 lost because of >1% gap-ups").
  Trade 35 (Nov-2023): yes – gap-ups 1.09% (15-Nov) and 1.65% (4-Dec), call-side stop. Trade 62 (Feb-2026): NO – it was a fall with three
  gap-DOWNS (−2.06% 2-Mar, −1.92% 4-Mar, −2.38% 9-Mar); its only gap-up (1.05% on 10-Mar) was a bounce after the damage; put-side loss.
  All 66 months at 300-pt, no filter: a >=1% gap-up during the trade 21 tr / 7 losers / −₹2,708; only gap-downs 11 tr / 6 losers / −₹1,425;
  no 1% gap 34 tr / 11 losers / +₹51,430 – months with any 1% gap make nothing. Ten worst: gap-up came first in 35, 19, 22, 15; gap-downs
  in 62, 16, 8, 52; no gap at all in 67 and 30. Inside the 36 months of the forward-test rule: 9 had a gap-up, only 1 lost (22). Gap-up 1%
  exit ON TOP of variant 6: ₹103,851 / DD −₹5,523 vs ₹114,939 / −₹5,523 → costs ₹11.1k (saves 22 +₹4.2k; cuts winners 3, 14, 56, 4, 61, 21,
  18). The ±2% filter already skips the gap-up losers 35, 19, 15, 16. Gap-up exit stays OFF; keep logging gap-up days in the journal.
  BAND 2–2.5% AT 300-PT WITH AN EARLY EXIT (13-Oct-2026, user idea: trade the months with a 10-day move of 2–2.5% at 300-pt and find an early
  exit for trade 35). The 8 band trades (2, 6, 15, 29, 35, 38, 41, 43) make −₹2,595 at 300-pt (35 −₹7,243, 15 −₹3,347, 41 −₹1,285). Early exits
  applied to the band trades only (band total / trades changed): gap-up >=1% → 15:16 exit +₹5,748 / 5 (35 −₹960 on 15-Nov-23, 15 −₹367; costs
  2, 43, 41 ≈ ₹0.3k each); NIFTY +2% above the entry-day close +₹4,516 / 4; NIFTY close >= sold CE − 100 +₹4,205 / 4; close >= sold CE or
  loss >= 30% of credit +₹1,180 / 3 (35 −₹4,058); loss >= 50% −₹770; gap-up >=1.5%, loss >= 75%, close >= bought CE ≈ no help (35 exits at −₹5.1k
  to −₹6.9k); "loss >= 25% by day 5" never fires. Trade 35's path: −10% of credit on the 15-Nov gap day, −14% to −26% for two weeks, −54% on
  29-Nov (close above the sold call), −96% on the 4-Dec gap (1.65%), stop 5-Dec – no loss-based signal before 29-Nov.
  Variant 6 + band at 300-pt (n / net / DD): no extra rule 44 / ₹112,344 / −₹7,243 (worse, a losing year); + gap-up 1% exit on the band only
  44 / ₹120,687 / −₹5,523 (with the 40% credit floor, i.e. without trade 29: 43 / ₹118,091); + NIFTY +2% exit 44 / ₹119,455 / −₹5,523.
  The same exits applied to EVERY month cost money (inside ±2%, 37 trades at 300-pt, base ₹68,646: gap-up 1% ₹62,660; sold CE ₹50,561; loss 30%
  ₹37,459; NIFTY +2% ₹39,231) – so they are only usable as a band-only rule. 2019–20 has one band trade (1903, +2.28%, −₹6,770): no 1% gap-up,
  so the exit does not save it; only the credit floor would (credit 36% of the 300-pt width). VERDICT: gain ≈ ₹3–6k over 6 years from 7–8
  trades, resting on trades 35 and 15; a rule chosen to catch one known trade. Not adopted – candidate to shadow-log (band month → note the
  300-pt condor and the first 1% gap-up day).
  C/W INSIDE THE MONTHS BEYOND ±2.5% (13-Oct-2026, user question; 21 months, 400-pt, TP 50%, total −₹21,675, 9 W / 12 L): C/W does NOT separate
  winners from losers – correlation with P&L 0.21, winners average 46.0% vs losers 43.9%, and the bands alternate: <40% 0 W / 2 L −₹8,116;
  40–42% 1 / 1 +₹3,676; 42–44% 0 / 3 −₹19,007 (36, 52, 62); 44–45% 3 / 1 +₹7,608; 45–47% 2 / 2 −₹5,920; 47–48.5% 0 / 2 −₹8,818 (16, 50); >=48.5%
  3 / 1 +₹8,901 (5, 13, 17, 63). Cumulative: >=45% 10 tr −₹5,837; >=46% −₹2,689; >=47% +₹83; >=48% 4 tr +₹8,901 / worst −₹1,673 – the only
  positive cut, and it is the known knife edge (trade 16 at 47.9% = −₹6,074; same finding as 8-Oct "rich credit at any move"). 2019–20 beyond
  ±2.5% (8 months, 400-pt): only 2004 is >= 48% (50.4%, +₹8,450); 2011 at 46.0% −₹9,068, 2007 at 45.9% +₹2,771. Not adopted; do not re-test.
  ENTRY 50–52 DTE / EXIT 25 DTE / TP 40% RESULT (18-Oct-2026, 400-pt, 64 common expiries, output/entry50_exit25_tp40_400pt.xlsx; n / net / max DD / losing years) – NOT ADOPTED, do not
  re-test: the requested timing (Monday 7 weeks before = 50–52 DTE, exit 25 DTE, TP 40%, SL 100%) is much worse under every filter. ±2.5% & C/W>=42%:
  38 / ₹50,978 / −₹7,491 / 2 vs current (43–45 → 18 DTE, TP 50%) 36 / ₹75,635 / −₹6,976 / 1. ±2% & C/W>=45%: 20 / ₹43,505 / −₹6,557 / 2 vs 17 / ₹55,646 /
  −₹1,558 / 0. ±2.5% only: 45 / ₹36,448 / −₹13,433 / 3 vs 44 / ₹83,114 / −₹9,814 / 1. No filter: ₹10,332 / −₹20,275 vs ₹59,670 / −₹14,946.
  Which part does the damage (±2.5% only, 400-pt): TP 50 → 40 at the current timing −₹8.5k (₹74,648); exit 18 → 25 DTE at the current entry
  −₹37.4k (₹45,692, 0 targets, 14 days held); entry a week earlier with exit 25 ₹39,726 – the extra early week adds nothing. The profit is
  made between 25 and 18 DTE. Earlier strikes are also thinner (14 trades on fallback strikes vs 2; 563 non-exact prices vs 378; 4 not run).
  Credit a little higher (187.5 vs 180.2 pts, C/W 46.9% vs 45.0%). TP 60% at the current timing ₹88,104 (±2.5%) – same as found before.
  RISK/REWARD 400-pt vs 600-pt on the forward-test rule (18-Oct-2026, output/risk_reward_400_vs_600.xlsx; 17 rich-credit months, TP 60%, rest of the
  rule 300-pt): whole rule ₹85,729 vs ₹114,939, both DD −₹5,523 (trade 67, 300-pt). Rich months: net ₹59,061 vs ₹88,271; W/L 14/3 vs 15/2; avg win
  ₹4,407 vs ₹6,068, avg loss −₹879 vs −₹1,372; worst −₹1,558 vs −₹2,045. Per condor: credit 191.5 vs 254.1 pts, C/W 47.9% vs 42.3%, max loss 208.5 vs
  345.9 pts (₹13,554 vs ₹22,485 at lot 65), credit÷max loss 0.92 vs 0.74; a 100% stop = credit ≈ ₹12,446 vs ₹16,515 at lot 65. Profit ÷ average
  max loss 5.2× vs 4.7× (per rupee at risk 400 is slightly better); wins needed to repay one stop ≈ 2.8 vs 2.7, one max loss ≈ 3.1 vs 3.7.
  Worst intra-trade dip (MAE) only 37% (400, trade 21) / 34% (600) of max loss – no rich month came near a stop. 600 = more absolute profit,
  same efficiency or slightly worse per rupee at risk, ≈ 1.7× the worst case and the margin. User's call; config holds 600 (variant 6).
  TREND-BIASED IC IN THE FILTER-SKIPPED MONTHS – RE-CHECKED 21-Oct-2026 (user asked again; same as the 29-Sep test, now with NSE closes and
  the current engine; 300-pt; 21 months beyond ±2.5%, 19 with data): normal condor −₹18,755 (19 common −₹17,527); A = trend-side leg moved
  out to 20Δ −₹27,207; B = trend side 20Δ + other side moved in to 35Δ −₹24,482. Whole strategy: skip ₹66,052 / −₹7,527; trade normal
  ₹47,298 / −₹11,860; A ₹38,844 / −₹13,187; B ₹41,570 / −₹12,779. Shifting cuts the credit (≈145 → 89–121 pts) so reversals hit the stop
  sooner (50: −₹2.4k → −₹9.8k / −₹10.4k; 48, 16, 8 stops). Helps the continued rallies (5, 36, 46, 28) but not enough. Do not re-test;
  400-pt version would need 141–201 calls and has the same mechanics.
  20Δ SOLD + 500-PT HEDGES IN THE FILTER-SKIPPED MONTHS (21-Oct-2026, user idea; strike set d20_skip, deltas 0.18–0.21; 20 of 21 months ran (1 no
  price), 4 on fallback strikes, 0 days with value > width; output/skipped_months_20delta_500pt.xlsx) – NOT ADOPTED, do not re-test, and 15Δ
  not worth downloading. 20 tr −₹42,030 / 10 W / 10 L / worst −₹10,622 vs the normal 30Δ/300-pt on the same months −₹19,358 / 8 W / 12 L.
  After a rise 17 tr −₹33,552 (30Δ −₹15,664); after a fall 3 tr −₹8,478 (−₹3,694). Exits 7 stop / 6 target / 7 time. Credit 121 vs 144 pts
  but max loss 379 pts (≈ ₹24.6k at lot 65) – credit ÷ max loss 0.32. More winners, much bigger losers: stops at −100% to −147% (62, 52, 50,
  19, 8, 9, 36). Whole strategy: skip ₹66,052 / −₹7,527; add 30Δ/300 ₹46,694 / −₹11,860; add 20Δ/500 ₹24,023 / −₹22,305.
  20Δ / 500-PT IN SKIPPED MONTHS WITH TIGHTER STOPS (21-Oct-2026; output/skipped_months_20delta_500pt_stops.xlsx; 20 trades): SL 100% −₹42,029
  (7 stops); SL 75% −₹37,286 (10 stops, worst −₹9,182); SL 50% −₹31,253 (11 stops, worst −₹9,182) vs 30Δ/300-pt SL 100% −₹19,357. Whole strategy
  (45 months inside ±2.5% at 300-pt + these): SL 50% ₹34,799 / DD −₹18,648 vs skipping ₹66,052 / −₹7,527. Tighter stops cut the big losers
  (52 −₹10.3k → −₹5.9k, 62 −₹10.6k → −₹6.4k, 19, 8) but stop out a winner (12 +₹2.3k → −₹5.2k) and with one check a day the stop overshoots
  (50: −94% of credit at the 50% stop). Still far worse than skipping. Not adopted; do not re-test.
  DIRECTIONAL STRUCTURES IN THE FILTER-SKIPPED MONTHS (21-Oct-2026, user request: credit spread vs hedged ratio spread, risk 3–4% of capital;
  2021–26, 21 months beyond ±2.5%, 1 lot, 11:16 entry, 15:16 check, 18-DTE exit; scratch simulator on cached candles, costs approximate;
  output/skipped_months_credit_vs_ratio_spread.xlsx) – NEITHER ADOPTED. Credit spread (put spread after a rise, call spread after a fall, 30Δ
  sold, TP 50% / SL 100% of its own credit; reproduces the 10-Oct test): 200-pt 21 tr −₹14,341 / DD −₹17,356, max loss ≈ ₹9.9k (lot 65); 300-pt
  −₹11,129 / DD −₹21,075, max loss ≈ ₹15.2k; put-after-rise only 300-pt 18 tr −₹5,024 (2021 +₹3.8k … 2025 −₹10.8k). Hedged ratio spread =
  broken-wing 1×2×1 in the direction of the move (after a rise: +1 CE 30Δ, −2 CE 20Δ, +1 CE 20Δ+500; mirror with puts after a fall): only 16
  of 21 run (no far-call price in 1, 8, 13, 19, 23), 16 tr −₹10,368 / DD −₹12,780 / worst −₹5,371 (33), debit ≈ 30 pts, max loss avg ₹11.5k,
  up to ₹19.7k (28: 200-pt inner gap); every trade a time exit – at 18 DTE the structure has barely moved (P&L −103 … +49 pts); a TP of 25% of
  max profit never fired. A ratio/butterfly earns in the last 2 weeks, which the 18-DTE exit gives away (holding longer needs data to
  expiry – not downloaded). Call broken-wing after a fall ("bounce"): 3 tr +₹509. Normal 30Δ/300 IC on the same months −₹18,755. Skipping = ₹0.
  HEDGED RATIO SPREAD HELD TO EXPIRY IN THE SKIPPED MONTHS (21-Oct-2026; data to expiry downloaded for 16 months; broken-wing 1×2×1 in the
  direction of the move: +1 30Δ, −2 20Δ, +1 20Δ±500; output/skipped_months_ratio_spread_to_expiry.xlsx; n=16, net / W-L / worst / DD):
  exit 18 DTE −₹10,368 / 6-10 / −₹5,371 / −₹12,780; 7 DTE −₹9,173; 3 DTE +₹2,296 / DD −₹8,868; EXPIRY +₹18,089 / 4-12 / −₹5,971 / −₹13,108;
  expiry + TP 50% of max profit +₹11,313 / DD −₹7,796; expiry + TP 25% −₹4,892; expiry + TP50 + SL 50% of max loss +₹7,006. By year (expiry):
  2021 +₹16.2k, 2022 −₹5.3k, 2023 +₹1.2k, 2024 −₹1.1k, 2025 +₹12.1k, 2026 −₹4.9k. LOTTERY-LIKE: the 4 winners are the months NIFTY finished within
  ≈200 pts of the sold strikes (57 +₹17.0k, 5 +₹13.2k, 28 +₹8.2k, 9 +₹4.2k = +₹42.7k); the other 12 lose about the debit (−₹0.5k…−₹3.1k; 33
  −₹6.0k with a 115-pt debit) because the move reversed. The max-loss case (finish beyond the far hedge) never happened. Theoretical max
  loss avg ₹11.5k, up to ₹19.7k (28, 200-pt inner gap). Whole strategy (45 months ±2.5% at 300-pt + these at expiry): ₹84,141 / DD −₹14,566
  vs skipping ₹66,052 / −₹7,527. NOT ADOPTED yet: 16 trades, profit from 3–4 of them, exit chosen after seeing the results, 2019–20 not
  tested (8 skipped months; needs data). Candidate to shadow-log in the forward test.
  RATIO SPREAD TO EXPIRY – TRADE BY TRADE (21-Oct-2026, output/ratio_spread_trade_by_trade.xlsx): result is decided by where NIFTY finishes.
  Near the sold strikes (±200 pts) 4 tr +₹42,656 (57, 5, 28, 9 – NIFTY carried on 2.8–6.5% in the direction; sold strikes were 3.5–6.6% away);
  past the sold strike towards the hedge 1 tr −₹450 (46); never reached the bought strike (move stalled or reversed) 11 tr −₹24,117, each
  ≈ the entry debit + costs (−₹670…−₹3,135; 33 −₹5,971 because its 500-pt inner gap made the debit 115 pts). Max-loss zone (beyond the far
  hedge) never reached. Trades 36 and 12 were near the sold strike mid-trade (+5.4%, +4.6%) but reversed by expiry. After a RISE (call
  version) 13 tr +₹23,654; after a FALL (put version) 3 tr −₹5,565 – the market bounced (52 +8.8%), as the direction study said. Entry VIX
  and the 10-day move do not separate winners from losers; winners had cheaper entries (debit avg 17 vs 34 pts).
  PUT CREDIT SPREAD AFTER A RISE WITH A 20Δ SOLD PUT (23-Oct-2026, user request; 18 skipped months after a 10-day rise > 2.5%, 2021–26; TP 50% /
  SL 100% of own credit, 18 DTE; all 18 ran; output/put_spread_20delta_vs_30delta_skipped_months.xlsx; net / W-L / max DD / worst / PF):
  20Δ 200-pt −₹3,286 / 12-6 / −₹7,765 / −₹3,210 / 0.75; 20Δ 300-pt −₹2,657 / 12-6 / −₹9,548 / −₹4,607 / 0.84; vs 30Δ 200-pt −₹10,238 / 10-8 /
  −₹13,253; 30Δ 300-pt −₹5,024 / 12-6 / −₹14,970. Drawdown about halves and the total loss shrinks, but it is still a loss: credit only 30 / 42
  pts (sold put 3.9% below spot vs 2.2% for 30Δ) against a max loss of 170 / 258 pts (≈ ₹11.1k / ₹16.8k at lot 65) – credit ÷ max loss 0.18 /
  0.16; average win ₹807 / ₹1,190 vs average loss −₹2,161 / −₹2,823. Same 6 losers at both widths (12, 16, 33, 48, 50, 62 – the reversal
  months), stops overshoot to −102%…−202% of credit. By entry period 2021–23 +₹2.3k / +₹4.2k, 2024–26 −₹5.6k / −₹6.8k. 0.5-pt slippage per leg
  → −₹5.2k / −₹4.6k. Not adopted; improvement ideas (VIX/50-DMA condition, lower target, NIFTY-level stop) still to revisit.
  PUT SPREAD AFTER A RISE – FILTERS TO SKIP REVERSALS AND EARLY EXITS (23-Oct-2026, user request; 18 months 2021–26; 20Δ 200 / 20Δ 300 / 30Δ 300;
  output/put_spread_filters_and_exits.xlsx; n / net / W-L / DD). Base TP50 SL100: 20Δ200 −₹3,286 / 12-6 / −₹7,765; 20Δ300 −₹2,657 / −₹9,548; 30Δ300
  −₹5,024 / −₹14,970. All 6 losers (12, 16, 33, 48, 50, 62) came after a 10-day rise in which VIX FELL 9.6–24.5% and NIFTY was barely above its
  50-DMA (avg +0.6% vs +3.5% for winners); their last-5-day move was small (avg +0.7% vs +2.5%) = the rally had already stalled.
  ENTRY FILTERS (TP50 SL100): VIX not down >10% in 10 days → 8 tr, 7-1: 20Δ200 +₹3,821 / −₹1,568; 20Δ300 +₹6,827 / −₹1,206; 30Δ300 +₹8,252 / −₹2,774.
  5-day move > +1% → 13 tr, 11-2: +₹5,469 / −₹1,891; +₹8,383 / −₹2,573; +₹12,672 / −₹3,630 (best balance of trades and result). 5-day > +1.5% 12 tr
  +₹4,626 / +₹7,159 / +₹10,795. NIFTY > 50-DMA by >2% 7 tr 6-1; >4% 6 tr 6-0; 60-day move > +2% 7 tr 6-1; 20-day move > +2% no help. VIX > −5% or
  50-DMA > 4%: 6 tr all winners (knife edge, tiny). EXITS (no filter): lower target + 50% stop helps – TP40 SL50 20Δ200 +₹3,224 / −₹1,848, 20Δ300
  +₹4,001 / −₹2,724; TP30 SL50 30Δ300 +₹4,244 / −₹4,347; SL 75% is worse than 50% and 100%; NIFTY-level exits (close below entry −2/−3%, below the
  sold put) only trim the 30Δ DD (−₹15.0k → −₹6.5k…−₹9.7k) with no profit; gap-down 1% exit much worse. COMBINED: mv5>1 + TP40 SL50 20Δ300 13 tr
  +₹6,471 / −₹1,799; 30Δ300 +₹7,783 / −₹2,493 (TP50 SL100 with mv5>1 is as good). 2019–20 CHECK (30Δ put spread, 5 rise months, all 5 targets: 300-pt
  +₹13,155, 400-pt +₹16,856): no losers there, so the filters only cut winners (VIX filter keeps 3, −₹5.2k; mv5>1 keeps 3; 50-DMA>2% keeps all 5).
  CAVEATS: 18 trades / 6 losers, thresholds read off the same data; VIX filter passes 0 of 4 rise months in 2025–26. Not adopted – best
  candidates to shadow-log: 5-day move > +1% at entry (and/or VIX not down >10%), 20Δ or 30Δ sold put, 300-pt hedge.
  PUT CREDIT vs CALL DEBIT vs HEDGED RATIO on the 13 months that pass "5-day move > +1%" (27-Oct-2026, user request; 2021–26, strikes from the
  reference 30Δ call and the d20_skip 20Δ legs; output/filtered13_put_spread_vs_call_debit_vs_ratio.xlsx; n / net / W-L / DD / avg max risk per lot at 65):
  PUT CREDIT 20Δ/300 TP50 SL100 13 / +₹8,383 / 11-2 / −₹2,573 / ₹16.7k; 30Δ/300 +₹12,672 / 11-2 / −₹3,630 / ₹15.4k. CALL DEBIT (buy 30Δ CE, sell 20Δ CE,
  debit ≈ ₹5.4k at lot 65, max ₹7.5k): hold to 18 DTE +₹10,765 / 7-6 / −₹7,195; TP 100% of debit / SL 50% +₹1,815 / 5-8; TP 50% / SL 50% +₹13,301 /
  9-4 / −₹5,664 (profit ÷ risk 2.47 vs 0.50–0.83 for the put spreads); hold to expiry +₹18,476 / 6-7 / −₹9,875. HEDGED RATIO (+1 30Δ, −2 20Δ, +1 20Δ+500
  calls; only 8 of 13 have a far-call price): 18 DTE +₹282; to expiry +₹25,420 / 3-5 / −₹4,950 (57 +₹14.3k, 5 +₹13.2k, 28 +₹8.2k); to expiry TP 50%
  +₹12,504. VERDICT: none lowers the DRAWDOWN below the put spread (−₹2.6k / −₹3.6k) – the put spread wins often and small; the call debit spread
  risks a third as much per trade (≈ ₹5.4k vs ₹16.7k), so its result per rupee at risk is much better and its worst case fits a 2% limit even
  at ₹3L, but it wins less often and its DD is larger in rupees. The ratio is a 3-winner lottery on 8 trades. All fitted on 13 trades;
  TP/SL for the debit spread chosen after seeing results. Not adopted – shadow-log candidates.
  PUT vs CALL CREDIT SPREAD IN ALL MONTHS THE FORWARD-TEST RULE SKIPS (27-Oct-2026, user request; 2021–26; skipped = |10-day move| > 2% or 400-pt
  C/W < 40%: 30 months; 30Δ sold, 300-pt hedge, TP50 SL100, 18 DTE; output/skipped_months_put_vs_call_credit_spread.xlsx; n / net / W-L / DD):
  PUT spread in every skipped month 30 / +₹7,936 / 22-8 / −₹10,659 (worst −₹6,129); CALL spread 30 / −₹18,738 / 17-13 / −₹30,722; normal 300-pt IC
  −₹20,491. By reason: rise > 2.5% (18) PCS −₹5,024 / CCS −₹2,576 (calls win the reversal months 12, 16, 33, 48, 50, 62 and lose the continuations);
  move 2–2.5% up (7) PCS +₹8,946 / 6-1 vs CCS −₹5,207; fall < −2.5% (3) PCS +₹2,226 (bounce) vs CCS −₹6,105; move −2…−2.5% (1, trade 41) PCS +₹974;
  C/W < 40% (1, trade 45) PCS +₹814 / CCS −₹2,602. Direction-matched (PCS after rise, CCS after fall) −₹3,617; against the move −₹7,185. Put spread
  in all skipped months + the 5-day filter (skip rise > 2.5% months whose last-5-day move <= +1%): 25 / +₹25,632 / 21-4 / −₹3,630; filter on every
  rise > 2%: 21 / +₹19,323 / −₹3,630. Credit avg PCS 65 / CCS 80 pts; max loss ≈ ₹15.3k / ₹14.3k at lot 65 (3–5% of ₹3–5L). Added to the variant-3
  forward rule (₹85,729): +PCS ≈ ₹93.7k; +PCS with 5-day filter ≈ ₹111.4k (combined drawdown not computed). CAVEATS: 5-day filter fitted on these
  months; 2019–20 put spreads after a rise all won (no test of the filter); NIFTY's upward drift in 2021–26 favours puts. Not adopted.
  PUT CREDIT vs CALL DEBIT SPREAD IN ALL 30 FORWARD-RULE SKIPPED MONTHS (27-Oct-2026, user request; 2021–26; PCS = sell 30Δ put / buy 300 lower,
  TP50 SL100; CDS = buy 30Δ call / sell call 300 higher, debit ≈ 80 pts ≈ ₹5.2k at lot 65 (max ₹7.3k); 18 DTE; output/skipped_months_put_credit_vs_
  call_debit.xlsx; n / net / W-L / DD / worst). ALL 30: PCS +₹7,936 / 22-8 / −₹10,659 / −₹6,129; CDS hold +₹17,799 / 13-17 / −₹15,478 / −₹5,678; CDS TP50
  SL50 +₹7,504 / 16-14 / −₹5,825 / −₹3,319; CDS TP100 SL50 +₹11,472 / 12-18 / −₹8,077. By reason: rise > 2.5% (18) PCS −₹5,024 / CDS hold +₹1,603 /
  TP50-SL50 +₹286 (DD −₹8.0k); rise 2–2.5% (7) PCS +₹8,946 / 6-1 vs CDS hold +₹11,844 / 3-4 (35 +₹10.5k); falls (4) CDS better (bounces: 52 +₹6.0k).
  With the 5-day filter on rise > 2.5% (25 tr): PCS +₹25,632 / 21-4 / −₹3,630; CDS hold +₹30,413 / 12-13 / −₹6,667; TP100 SL50 +₹17,355 / −₹5,245.
  PCS = higher win rate and the lowest drawdown in rupees, but ≈ ₹15.3k at risk per trade; CDS = about a third of the risk per trade (fits 2%
  of ₹3L), wins less than half the time, profit per rupee at risk far higher (filtered: CDS ≈ 5.9× its average risk vs PCS ≈ 1.7×). Not adopted.
  20Δ PUT CREDIT SPREAD vs CALL DEBIT SPREAD HELD TO 18 DTE (27-Oct-2026, user's two candidates; 20Δ puts only exist for the 18 rise > 2.5% months;
  output/put20_credit_vs_call_debit_hold18.xlsx; n / net / win / DD / worst / PF / risk per lot at 65). 18 rise months: PCS 20Δ/200 −₹3,286 / 67% /
  −₹7,765 / −₹3,210 / 0.75 / ₹11.1k; PCS 20Δ/300 −₹2,657 / −₹9,548 / ₹16.8k; CDS (buy 30Δ call, sell +300) +₹1,603 / 44% / −₹17,356 / −₹5,678 / 1.05 /
  ₹5.2k. 13 months with the 5-day filter: PCS 20Δ/200 +₹5,469 / 85% / −₹1,891 / −₹1,891 / 2.53; PCS 20Δ/300 +₹8,383 / 85% / −₹2,573 / 2.71; CDS +₹14,217 /
  54% / −₹6,004 / −₹5,174 / 1.94. CDS profit is concentrated in 2021 (+₹14.0k of +₹14.2k; 2025–26 −₹2.7k) while PCS 20Δ is positive in 2025–26
  (+₹1.9k / +₹2.9k). Avg win/loss: PCS 20Δ/200 ₹822 / −₹1,786; CDS ₹4,199 / −₹2,530. Not run yet: 20Δ PCS in the other 12 skipped months (2–2.5%
  band, falls, C/W < 40%) – needs 20Δ put strikes for 9 months + hedges for 12.
  20Δ PUT CREDIT SPREAD IN ALL 30 FORWARD-RULE SKIPPED MONTHS (27-Oct-2026; strikes d20_skip + d20_rest (9 new months); 200 and 300-pt hedges;
  trade 41 has no 300-pt hedge price; output/put20_credit_spread_all_skipped_filters.xlsx; n / net / W-L / DD / worst; TP50 SL100 unless stated).
  No filter: 200-pt 30 / +₹3,359 / 23-7 / −₹6,318 / −₹3,210; 300-pt 29 / +₹5,306 / −₹7,895. 5-DAY FILTER (skip rise > 2.5% months whose last 5 days
  added <= +1%): 200-pt 25 / +₹12,114 / 22-3 / −₹1,891 / −₹1,891, every year positive (2021 +₹2.6k, 2022 +₹4.5k, 2023 +₹1.0k, 2024 +₹0.9k, 2025 +₹2.2k,
  2026 +₹0.9k); 300-pt 24 / +₹16,346 / 21-3 / −₹2,573. By group (200-pt, filtered): rise > 2.5% 13 tr +₹5,469; rise 2–2.5% 7 tr +₹5,020; falls 4 tr +₹1,274;
  C/W < 40% 1 tr +₹351. Filter on every rise > 2% (also the band): 21 tr +₹9,355 / −₹1,891 (worse – band months with a small 5-day move won).
  Other filters (200-pt): VIX <= 20 −₹2,107 (no); VIX <= 22 +₹993; VIX not down >10% 18 tr +₹8,699 / −₹2,536; above 50-DMA 20 tr +₹7,571 / −₹1,838;
  sold put below 20-day low 9 tr −₹5,132 (no); spread credit >= 15% of width 12 tr +₹6,835 (300-pt only 4 tr). ON TOP of the 5-day filter: + VIX not
  down >10% 16 tr +₹9,625 / DD −₹968 (fewest losses, fewer trades); + above 50-DMA 17 tr +₹10,335 / −₹1,680; + VIX <= 22 22 tr +₹9,748; + credit >= 15%
  11 tr +₹8,673 / 11-0. Exits: TP40 SL50 helps only without a filter (200-pt +₹7,122 / −₹2,380); with the 5-day filter it lowers profit (₹9,066).
  Risk per lot (65): 200-pt ≈ ₹11.1k (3.7% of ₹3L, 2.2% of ₹5L), 300-pt ≈ ₹16.9k. Candidate for the shadow log: 20Δ/200 put spread in every skipped
  month, skipping rise > 2.5% months with 5-day move <= +1%. Not adopted (fitted on 30 months; 2019–20 not tested at 20Δ).
PUT CREDIT SPREAD IN THE 2019–20 FORWARD-RULE SKIPPED MONTHS – 30Δ PREVIEW (27-Oct-2026; cached data; 20Δ needs strike selection + candles).
2019–20: the forward rule skips 20 of 24 months – 13 of them only because the 400-pt C/W was < 40% (thin credit; in 2021–26 only 1 such month).
30Δ sold put, TP50 SL100, 18 DTE, lot 75 (output/put30_spread_2019_2020_skipped_months.xlsx; n / net / W-L / DD / worst): 300-pt 18 / +₹1,639 / 13-5 /
−₹15,388 / −₹8,306; 400-pt 16 / +₹4,184 / −₹12,630 / −₹10,580. Rise > 2.5% months 5 / +₹13,155 / 5-0 (300-pt); all OTHER skipped months 13 / −₹11,516 /
8-5 / DD −₹23,185 – stops 1907, 1908, 2002, 2003 (COVID), 2009. The 5-day filter only removes two winners (1911, 2006) → 16 / −₹3,548 / DD −₹20,575.
WARNING for the "put spread in every skipped month" idea: the thin-credit (C/W < 40%) and non-rise months were the losers in 2019–20.
COMBINED: FORWARD-RULE IC + 20Δ PUT SPREAD IN ITS SKIPPED MONTHS (27-Oct-2026, 2021–26, 1 lot, net, one position per month – they never overlap;
IC = variant 3 (400-pt TP 60% if C/W >= 45%, 300-pt if 40–45%, |move| <= 2%); PCS = 20Δ put spread TP50 SL100 18 DTE in the other months, skipping
rise > 2.5% months with 5-day move <= +1% (9, 16, 48, 50, 62); output/combined_ic_plus_put20_spread.xlsx; n / net / W-L / max DD / worst / PF):
IC only 36 / ₹85,729 / 28-8 / −₹5,523 / −₹5,523 / 5.67. + PCS 200-pt 61 / ₹97,843 / 50-11 / −₹5,523 / −₹5,523 / 5.27. + PCS 300-pt (41 no price) 60 /
₹102,075 / 49-11 / −₹5,523 / 5.18. The put spreads add ₹12.1k / ₹16.3k without deepening the drawdown (still trade 67); every year positive (2022:
IC +₹0.7k, PCS +₹4.5k / +₹6.5k). CAVEAT: 5-day filter fitted on these months; 2019–20 not tested at 20Δ (30Δ preview lost in thin-credit months).
20Δ PUT CREDIT SPREAD IN THE 2019–20 FORWARD-RULE SKIPPED MONTHS (27-Oct-2026; strike set d20_2019_2020, deltas 0.18–0.22; lot 75; TP50 SL100,
18 DTE; output/put20_credit_spread_2019_2020_skipped_months.xlsx; n / net / W-L / DD / worst). 20 skipped months; not run: 2003 (Mar-2020 crash, no
price), 1905 and 2004 at 200-pt (no hedge price; fallback not simulated). 5-DAY FILTER (removes 1911, 2006 – both winners): 200-pt 15 / +₹2,795 /
12-3 / −₹5,280 / −₹4,487; 300-pt 17 / +₹9,285 / 14-3 / −₹7,028 / −₹6,349. No filter: 200-pt 17 / +₹5,064; 300-pt 19 / +₹12,529. Losers: 1907
(Jul-19, −3.1% fall, −₹3,052 / −₹4,169), 1909 (Sep-19, −3.4% in 3 days, −₹2,334 / −₹3,210), 2009 (Sep-20, −5.8%, −₹4,487 / −₹6,349; stops at −112…−212%
of credit). By group (200-pt, filtered): rise > 2.5% 4 / +₹4,789 / 4-0; C/W < 40% 9 / +₹29 / 7-2; move 2–2.5% 2 / −₹2,023. Feb-2020 (2002) took its
target on 12-Feb, before the COVID fall (30Δ: −₹5,694 stop). 30Δ preview on the same months: 300-pt 18 / +₹1,639 / DD −₹15,388 → 20Δ is much safer.
Combined with the 4 forward-rule condors (+₹7,040): 200-pt 19 tr +₹9,835 / DD −₹5,280 (2019 +₹2.3k, 2020 +₹7.5k); 300-pt 21 tr +₹16,325 / DD −₹7,028.
Risk per lot at 75: ≈ ₹13.0k (200) / ₹19.6k (300). On top of 5-day: above 50-DMA 11 tr +₹6,586 (200); VIX not down >10% 7 tr +₹863 – no help.
VERDICT: the 20Δ/200 put spread with the 5-day filter stays profitable out of sample (small, +₹2.8k), with a drawdown inside the 2021–26 condor's
−₹5.5k; thin-credit calm months are about break-even. Caveat: the crash month 2003 could not be priced (30Δ lost −₹5,315 there).
WHOLE RULEBOOK 2019–26 – FALLBACK, SLIPPAGE, THIN-CREDIT PUT SPREADS (28-Oct-2026, points 2–4 of the improvement list; condor = variant 3, put spread
20Δ TP50 SL100 with the 5-day filter; new module ic/spread_sim.py = the put-spread simulator; output/rulebook_2019_2026_fallback_slippage_thin_credit.xlsx).
(2) FALLBACK STRIKES for put spreads (move the spread −50/+50/−100/+100, then widen the hedge +50/+100): reproduces every earlier result within ₹0.5 and
adds 1905 (200-pt → 300-pt hedge, +₹3,171), 2004 (spread 100 pts out, 7700/7500, +₹3,737), 41 at 300-pt (100 closer, +₹551). 2003 (Mar-2020 crash) still
has no price except the sold put – untestable. Rulebook, 200-pt put spread (n / net / DD / worst / PF): 2021–26 61 / ₹97,843 / −₹5,523 / −₹5,523 / 5.27;
2019–20 21 (4 IC + 17 PCS) / ₹16,742 / −₹5,281 / −₹4,487 / 2.41; 2019–26 82 / ₹114,585 / −₹5,523 / 4.30, no losing year. 300-pt: 2021–26 ₹102,625;
2019–20 ₹16,324 / −₹7,028; 2019–26 ₹118,949 / −₹7,028.
(3) SLIPPAGE per leg per fill (condor 8 fills, put spread 4): 0.5 pt → 2021–26 ₹87,353 / DD −₹5,783 (300-pt ₹92,135); 2019–26 ₹100,345; 1 pt → ₹76,863 /
−₹6,043; 2019–26 ₹86,105. No losing year at 1 pt. Break-even slippage: condor ≈ 5.0 pts/leg, put spread 2.2 (200-pt) / 2.6 (300-pt) – the put spread
loses ≈ 20% of its profit per 0.5 pt. Live NSE quote (27-Oct, Dec expiry): the 20Δ/200 spread's half bid-ask ≈ 1.3 pts/leg, so crossing the spread on
entry and exit would take most of its edge → use limit orders near mid for the put spread.
(4) NO PUT SPREAD IN THIN-CREDIT-ONLY MONTHS (|move| <= 2%, 400-pt C/W < 40%): 10 months (9 in 2019–20, +₹29; trade 45 +₹351). 200-pt: 2019–26 72 tr
₹114,204 / −₹5,523 / PF 5.09 vs base 82 tr ₹114,585 / PF 4.30; 2019–20 DD −₹5,281 → −₹3,052; with 0.5-pt slip it is +₹1.0k better (₹101,364 vs ₹100,345).
Same profit, 10 fewer trades, smaller 2019–20 drawdown. CAVEAT: 9 of the 10 months are 2019–20, where C/W < 40% came mostly from the fixed 400-pt width
being wide at NIFTY 10–12k (the %-width question), not from cheap premium. Dropping a PCS when credit was low for a big-move month (e.g. 8, 28, 1910) is NOT
the same rule and was not adopted. Not adopted – user's call.
USER DECISION 28-Oct-2026: NO credit (C/W < 40%) filter on the put spread – 9 of the 10 affected months are 2019–20, where the low ratio came from the fixed
400-pt width at NIFTY 10–12k. The put spread trades in every condor-skipped month except the 5-day-filter skips. Do not propose it again.
PUT SPREAD TARGET × EXIT DTE WITH THE 5-DAY FILTER (28-Oct-2026, point 5; 20Δ, SL 100%, fallback strikes; 2021–26 25 tr + 2019–20 17 tr = 42;
output/put_spread_target_exitdte_5day_2019_2026.xlsx; net 2021–26 / DD 2021–26 | net 2019–20 / DD 2019–20 | 2019–26 net). 200-pt, 18 DTE: TP 30% ₹8,234 /
−₹1,891 | ₹7,077 / −₹4,487 | ₹15,311; TP 40% ₹11,234 / −₹1,891 | ₹10,501 / −₹4,487 | ₹21,735 (hold 7.8 days); TP 50% ₹12,114 / −₹1,891 | ₹9,702 / −₹5,281 |
₹21,816 (10.7 days); TP 60% ₹10,245 / −₹4,384 | ₹21,305; TP 70% ₹20,771; no target ₹13,895 / −₹4,384 | ₹10,797 | ₹24,692 (time exit only, 22.6 days).
21 DTE ≈ ₹1k less at every target; 25 DTE much worse (₹8–14k). 300-pt, 18 DTE: TP 40% ₹22,973; TP 50% ₹26,181 (best); TP 60% ₹15,840 / DD −₹6,119 (2021–26);
no target ₹25,440 / −₹6,119. VERDICT: keep TP 50% and 18 DTE. TP 40% ≈ the same at 200-pt (−₹81 over 8 years, smaller 2019–20 DD, 3 days shorter) –
equivalent alternative; above 50% the 2021–26 DD more than doubles (trades held into the late losses). Do not re-test.
PUT SPREAD SOLD DELTA 15 / 20 / 25 (28-Oct-2026, point 6; condor-skipped months, 5-day filter, TP50 SL100, 18 DTE, fallback strikes; output/
put_spread_15_20_25_delta_2019_2026.xlsx; net 2021–26 / DD | net 2019–20 / DD | 2019–26). 15Δ/200 −₹316 / −₹3,090 | +₹6,595 / −₹3,665 | ₹6,279 (credit 21 pts,
6 stops in 23); 15Δ/300 ₹10,374 / −₹2,152 | ₹1,951 / −₹6,400 | ₹12,325. 20Δ/200 ₹12,114 / −₹1,891 | ₹9,702 / −₹5,281 | ₹21,816; 20Δ/300 ₹16,896 / −₹2,573 |
₹9,284 / −₹7,028 | ₹26,181. 25Δ/200 ₹14,892 / −₹2,358 | ₹5,513 / −₹9,756 | ₹20,405; 25Δ/300 ₹29,338 / −₹2,999 (PF 7.6) | −₹1,764 / −₹18,552 | ₹27,575.
VERDICT: 20Δ is the only delta that is solid in BOTH periods; 15Δ collects too little (stops at the same rate), 25Δ/300 is the best 2021–26 result but loses
out of sample with a −₹18.6k drawdown. Keep 20Δ/200. Do not re-test.
WALK-FORWARD OF THE RULEBOOK THRESHOLDS (28-Oct-2026, point 1; 900 rules = 10-day limit 1.5–2.5% × rich line 43–47% × floor 36–42% × put-spread rise
2/2.5/3% × 5-day limit 0.5/1/1.5%; every month's condor 400 (TP60; 2019–20 TP50) / condor 300 / 20Δ-200 put spread priced; output/
walk_forward_rulebook_thresholds.xlsx). ALL 900 rules are profitable in every period (2021–23, 2024–26, 2019–20); grid medians 2021–26 ₹88.1k / DD −₹5.5k,
2019–20 ₹18.8k. Fit on 2021–23 → best rule (1.75%, 43%, 42%) makes ₹60.6k / −₹7.0k in 2024–26 vs the adopted rule ₹68.2k / −₹5.5k (adopted beats 81% of the
grid there); fit on 2024–26 → ₹28.5k / −₹4.9k in 2021–23 vs adopted ₹29.7k / −₹3.7k (beats 98%); fit on 2021–26 → ₹28.1k in 2019–20 vs adopted ₹16.7k (beats 32%,
because a lower floor turns the 2019–20 thin-credit months into 300-pt condors – the %-width effect). Re-optimising does NOT beat the adopted thresholds out of
sample: the result comes from the structure, not the exact numbers. One-at-a-time (2021–26 / 2019–20): move limit 1.5% ₹87.6k, 1.75–2% ₹98k, 2.25–2.5% DD
−₹9.1k (trade 35 enters) – the only cliff; rich 43% ₹101.8k but DD −₹7.0k; floor 36–40% same in 2021–26, 42% ₹84.1k; rise 2/2.5/3% and 5-day 0.5/1/1.5%
within ±₹3k. Put spread in the 40 condor months instead of the condor: +₹4.0k (2021–26, 36 tr, DD −₹9.2k) vs condors ₹85.7k → condor is right in calm months.
VERDICT: thresholds robust; keep them. Do not re-test.
HEDGE WIDTHS AS A % OF NIFTY (28-Oct-2026, point 7, user idea; whole rulebook re-simulated with ic/spread_sim.py incl. per-side fallback; widths =
% × NIFTY at entry rounded to 100 (min 100); A = calibrated to the 2021–26 average NIFTY 20,530 (wide 1.95% / normal 1.46% / put spread 0.97%), B = to
today's 22,500 (1.78 / 1.33 / 0.89%); output/percent_width_hedges_2019_2026.xlsx; n / net / DD / worst / PF). Same simulator, fixed 400/300/200: 2021–26 61 /
₹97,350 / −₹5,503 / 5.26 (engine ₹97,843 – simulator validated); 2019–20 21 / ₹16,700 / −₹5,281; 2019–26 ₹114,050. % A: 2021–26 ₹84,192 / −₹6,959 / 4.07;
2019–20 19 / +₹406 / −₹11,452 (a losing year); 2019–26 ₹84,598 / −₹11,452. % B: 2021–26 ₹83,242 / −₹5,503; 2019–20 −₹830 / −₹11,452; 2019–26 ₹82,412.
WHAT HAPPENS: the C/W ratio does become level-independent (median 45–48% in both periods vs 45% / 37% with fixed widths), so in 2019–20 the credit test
now passes and 7–8 thin-credit months switch from put spread to a 200-pt condor – those condors made less (2002 Feb-2020 −₹6,902 vs put spread +₹1,489;
1910 −₹2,553). In 2021–23 the widths shrink to 200–300 pts, and narrower hedges earn less (same as the 200/300/400 ladder). VERDICT: % widths cost ₹13–14k
in 2021–26 and ≈ ₹16k in 2019–20 and double the drawdown – NOT adopted; keep fixed 400/300/200. The level question stays real: re-check widths at the
6–12-month review or if NIFTY moves more than ≈ 20% from 22,500 (credit/width drifts with the level). Do not re-test.
APR-2026 EXPIRY PUT SPREAD (28-Oct-2026; entry Mon 16-Mar-2026, expiry 28-Apr, time exit 10-Apr; trade set apr26, strike set d20_apr26). Filter: 10-day
move −9.20%, 5-day −5.31% → no condor; a fall, so the 5-day check does not apply → the rule TRADES the 20Δ/200 put spread. NOT TESTABLE on Breeze data:
on 16-Mar only round strikes traded (22000, 22300, 22400 PE); the picked put is 22000 at 0.24Δ (the ~20Δ strikes 21600–21950 had no trades); the
200/300-pt hedges 21800/21700 had NO trades until 23-Mar, and 23-Mar shows an impossible 22000/21800 spread value of 354 pts on a 200-pt width (bad
print). Rough indication only (entry on 24-Mar instead, 22000/21800 ≈ 45 pts credit): worst mark 30-Mar ≈ −51% of credit (NIFTY low close 22,331 stayed
above 22,000), target reached ≈ 8-Apr as NIFTY rallied to 24,051 → probably a ≈ +₹2k winner, but it rests on thin, partly bad prints. Kept OUT of all
totals (rulebook stays 61 tr ₹97,843 for 2021–26). Live lesson: after a crash far puts trade only on round 100/500 strikes – use the chain's bid/ask.
SECOND ENTRY TWO WEEKS LATER, EXIT 18 DTE (28-Oct-2026, point 8 part 1; trade set w4 = Monday 4 weeks before the expiry week, 28–31 DTE, 90 trades,
id = expiry YYMM; strike sets d30_w4 / d20_w4; full rulebook applied at the second entry with its own 10-day / 5-day readings and 400-pt credit test;
1 lot each; ic/spread_sim.py; output/second_entry_2weeks_18dte.xlsx; n / net / DD / worst / PF; DD in exit-date order). Second entry alone: 2021–26 59 /
+₹3,680 / −₹22,197 / −₹4,189 / 1.10 (2 losing years); 2019–20 22 / +₹919 / −₹14,652. At 29 DTE the 400-pt credit is thinner (C/W median 41.8% vs 44.3%), so
60 of 81 become put spreads (2021–26: 39 tr −₹2,056) and only 21 condors (2021–26: 20 tr +₹5,735 / DD −₹6,707; all time exits – 11 days is too short for a
target). Combined A + B, 2021–26: all 120 tr ₹101,030 / DD −₹10,287 vs A alone 61 tr ₹97,350 / −₹5,503; B condor only 81 tr ₹103,085 / −₹10,287; 2019–20 A+B
₹17,618 / −₹15,203 vs A ₹16,700 / −₹5,281. 0.5-pt slippage on B's extra fills (≈ ₹5k on its 20 condors) removes the gain. VERDICT: about +₹4–6k over six years
for twice the drawdown, twice the margin in overlapping weeks and 20–60 more trades – NOT adopted. Part 2 (exit 7 DTE) below.
SECOND ENTRY TWO WEEKS LATER, EXIT 7 DTE (28-Oct-2026, point 8 part 2; same w4 entries and rulebook, time exit at 7 DTE instead of 18; normal entry A
unchanged at 18 DTE; output/second_entry_2weeks_7dte.xlsx; n / net / DD / worst / PF). Second entry alone: 2021–26 59 / +₹44,127 / −₹20,213 / −₹11,247 / 1.87
(18 DTE: +₹3,680); 2019–20 22 / +₹11,010 / −₹13,295. By structure 2021–26: 400-pt condors 7 tr +₹35,890 (4 targets, held ≈ 21 days); 300-pt condors 13 tr
+₹2,543 incl. two stops near the full max loss (2510 −₹11,247, 2603 −₹11,198) and 2609 −₹6,840; put spreads 39 tr +₹5,694 (DD −₹12.4k alone). Combined A + B:
2021–26 120 tr ₹141,477 / DD −₹14,748 / worst −₹11,247 / PF 2.92 vs A alone ₹97,350 / −₹5,503 / 5.26; 2019–20 ₹27,710 / −₹13,846 vs ₹16,700 / −₹5,281; slippage
0.5 pt ₹122.4k / −₹15.3k, 1 pt ₹103.4k / −₹15.9k (A: ₹86.9k / ₹76.4k). Hindsight subset 'B only when it is a 400-pt condor': 2021–26 68 tr ₹133,240 / −₹5,503
(7 trades, 6 winners; 2019–20 had none, so untested out of sample). WHY: the profit comes from holding through 18 → 7 DTE (the last-two-weeks gamma zone
the 18-DTE rule avoids) – more targets, but the losers run to max loss (worst trade doubles, DD ≈ 2.7×). The normal entry was never tested below 17 DTE
(no data), so part of the gain may simply be 'exit later', not 'second entry'. VERDICT: big extra profit (+₹44k) for a ≈ ₹15k drawdown, ₹11k single
losses and two positions for two weeks – NOT adopted (fails the 2–3%-max-loss rule of thumb at ₹3–5L). Candidate to shadow-log: the 400-pt condor at the
second entry held to 7 DTE.
TRADE 45 DATA CORRECTION (29-Oct-2026, user check; entry 16-Sep-2024, Oct-2024 expiry): the 26450 CE (400-pt call hedge) shows 114.65 at 11:16 – a stale
quote with zero volume on 16 and 17 Sep, priced above the nearer 26400 CE (102.00). With it the 400-pt credit is 158.55 = 39.6% → below the floor → put
spread (+₹351). Realistic 26450 CE = 92.75 (midway 26400 CE 102.00 / 26500 CE 83.50, both heavily traded) → credit 180.45 = 45.1% → 400-pt IC, TP 60%: worst
−48% on 27-Sep, time exit 11-Oct +46.45 pts, net ₹942 (300-pt IC would be ₹854; 0.45 pt above the 45% line). output/combined_ic_plus_put20_spread.xlsx
updated (Changes sheet): COMBINED IC + PCS 200 2021–26 61 tr ₹97,843 → ₹98,434 (37 IC + 24 PCS), IC + PCS 300 ₹102,075 → ₹102,510, DD unchanged −₹5,523.
Other quoted rulebook totals (₹97,843, 2019–26 ₹114,585 etc.) are BEFORE this fix (+₹591). The engine's bad-print rule only catches a hedge priced >= its
own sold leg; a hedge priced above a nearer strike or with zero volume is not caught (proposed check, not built).
TRADE 38 300-PT PCS CORRECTION (29-Oct-2026; Mar-2024 expiry, alternative column only): 20650 PE showed 114.50 at 11:16 (stale, zero volume/OI, above
20750 PE 104.00) → credit 29.60 < the 200-pt spread's 40.10. Realistic 91.15 (midway 20700 / 20600 PE) → credit 52.95, target 19-Feb, net ₹1,216 (was ₹787).
COMBINED IC + PCS 300 2021–26 → ₹102,939; official IC + PCS 200 unchanged ₹98,434.
LOT SIZE FIX (29-Oct-2026, user check, NSE circular NSE/FAOP/47854 of 31-Mar-2021): NIFTY's lot was 75 for every contract expiring up to the
Jun-2021 expiry; 50 only from the Jul-2021 expiry. config.LOT_SIZES had 50 from the Feb-2021 expiry (StockMock's quantity) → trades 1–5 (Feb–Jun 2021
expiries) were a third too small. Fixed in ic/config.py (75 up to 2021-06-24). All five were winners, so 2021–26 profits rise, drawdowns unchanged:
main report 300-pt ±2.5% 45 tr ₹66,052 → ₹69,855 / DD −₹7,527 / PF 3.32; 400-pt ±2.5% ₹83,114 → ₹87,879 / −₹9,814; no filter 300-pt ₹47,298 → ₹50,851 /
−₹11,860; 400-pt ₹61,439 → ₹66,440 / −₹14,946. Forward rule (output/combined_ic_plus_put20_spread.xlsx, also incl. the trade 38/45 price fixes): IC only
37 tr ₹90,667; COMBINED IC + PCS 200 61 tr ₹103,880 / DD −₹5,523 / PF 5.54; IC + PCS 300 ₹108,959. Put spreads (output/pcs_trade_details.xlsx): 2021–26
200-pt 24 tr ₹13,212, 300-pt ₹18,842 (incl. trade 41 on fallback strikes). Trade by trade at 75: 1 PCS ₹1,109 → ₹1,711; 2 PCS ₹664 → ₹1,043; 3 IC 400
₹5,146 → ₹7,814; 4 IC 400 ₹2,469 → ₹3,798; 5 PCS ₹843 → ₹1,312. ALL 2021–26 totals quoted in the entries above this one used lot 50 for those five
months – add roughly ₹3–5.5k (depending on which of 1–5 a rule trades) when comparing. 2019–20 unchanged. Old reports kept in output/pre_lotfix/.
ENTRY-DAY CHECK FIX IN ic/spread_sim.py (29-Oct-2026, user check): the put-spread simulator started its daily 15:16 checks the day AFTER entry; the
engine (ic/engine.py) checks the entry day too. Fixed (entry <= day <= time exit). Re-run of output/pcs_trade_details.xlsx: no 2021–26 trade changes; in
2019–20 only 2004 (Apr-2020, COVID) changes – and its put prices are unusable (7800 PE 9 trades / 7700 PE 3 trades on 13-Apr-2020, 7700 priced above 7800,
7800 196 → 280 intraday with NIFTY flat; only 8000/7500 traded normally). 2004 is now NOT TESTABLE and out of the totals (its earlier +₹3,737 at 200-pt
rested on the same prints). Put spreads 2019–20: 200-pt 16 tr ₹5,965 / DD −₹5,281 (was 17 tr ₹9,702); 300-pt 16 tr ₹7,278 / −₹7,028. So the 2019–20 /
2019–26 rulebook totals quoted above (e.g. 2019–20 ₹16,742, 2019–26 ₹114,585) include ≈ +₹3.7k from 2004 that should be removed. Studies run with the
old simulator (points 7 and 8) did not check entry days – re-run them before relying on small differences.
VARIANTS 3–6 RE-RUN WITH THE 29-OCT CORRECTIONS (29-Oct-2026, user request; output/variants_400_500_600_corrected.xlsx; 2021–26, ±2%, 400-pt credit test; n /
net / max DD / worst / W-L / PF / 0.5-pt slip). Lot 75 for Feb–Jun 2021 (trades 3, 4 are rich months) and trade 45 now rich – its far call hedge was stale at
every width (400-pt 26450 CE 114.65 → 92.75; 500-pt 26550 CE 157.40 from one 09:29 trade, above 26500 → 73.80 = midway 26500/26600, stale 16–19 Sep; 600-pt
26650 CE 44.05 zero volume, below 26700 → 58.33, stale 16–17 Sep); credits 180.45 / 214.1 / 245.5, nets ₹942 / ₹1,229 / ₹1,541 (the engine's raw 500-pt run
books an impossible −₹4,363 stop). 18 rich + 19 at 300-pt = 37 condors. (3) 400 when rich 37 / ₹90,667 / −₹5,523 / −₹5,523 / 29-8 / 5.94 / ₹82,307; (4) 500 on all
37 / ₹116,055 / −₹9,515 / −₹9,515 / 30-7 / 4.88 / ₹107,695; (5) 500 when rich 37 / ₹106,462 / −₹5,523 / 6.81 / ₹98,102; (6) 600 when rich 37 / ₹122,477 / −₹5,523 /
7.63 / ₹114,117 (before: ₹85,729 / ₹110,219 / ₹100,287 / ₹114,939). Rich months 400 vs 600: ₹64,000 vs ₹95,809, W/L 15/3 vs 16/2, avg win ₹4,442 vs ₹6,160, avg
loss −₹879 vs −₹1,372, worst −₹1,558 vs −₹2,045, credit 190.9 vs 253.6, max loss 209.1 vs 346.4 pts (≈ ₹13.6k vs ₹22.5k at lot 65), credit ÷ max loss 0.91 vs
0.73, rich profit ÷ avg max loss 5.5× vs 5.0×. Same picture as before; summary page updated. Version B estimate (600 + 300-pt PCS) ≈ ₹1.41L.
  FINALISED by the user 11-Oct-2026: "±2% both" (400-pt if credit>=45%, 300-pt if 40–45%, skip below 40%; `FWD_NARROW_MOVE_PCT` 1.5 → 2.0).
  Details behind it are listed in §1b "Small print": trade 24 (no Breeze data) would have been a 300-pt trade (move −0.09%, StockMock
  credit 177.7 pts = 44.4%, StockMock −₹1,925 gross) → 2021–26 ≈ ₹83.5k, 2022 ≈ −₹1.5k, DD ≈ −₹5.8k; trade 35 at 2.00% would give
  ≈ ₹78.5k / −₹7.4k; trade 30 passes the floor by 0.2 pt (40.05%, −₹3,731); trade 45 fails it at 39.6% (+₹859, odd hedge print).
  500-PT HEDGES ON THE 17 RICH-CREDIT MONTHS (11-Oct-2026, user idea; NIFTY, the months the §1b rule trades at 400-pt: |10d move| <= 2%
  and 400-pt credit >= 45%; stop 100%; 500-pt hedges downloaded for all 67 months; output/nifty_hedge500_vs_400_rich_credit_trades.xlsx;
  net / max DD / worst / win / targets). 400-pt TP 50% ₹55,646 / −₹1,558 / −₹1,558 / 82% / 6; 400-pt TP 60% ₹59,061 / same / 3;
  500-pt TP 50% ₹70,204 / −₹1,815 / −₹1,815 / 88% / 7; 500-pt TP 60% ₹73,619 / same / 3. 500 beats 400 on 15 of 17 trades (+₹14.6k);
  credit 224.5 vs 191.5 pts, maximum loss per condor 275.5 vs 208.5 pts (+32%). Whole §1b rule with 500 instead of 400 on those
  months: 36 tr ₹100,287 (TP 60%) / DD −₹5,523 vs ₹85,729 / −₹5,523 (the drawdown is trade 67, a 300-pt trade). Only 1 of the 17 needed
  a fallback strike (53); over all 67 months 6 did, all on the call side. CAVEATS: these 17 months contain only 3 losers, the
  largest −₹1,815, so the test says nothing about a bad month at 500-pt – over all 66 months with no filter 500-pt is ₹71,053 /
  DD −₹16,938 / worst −₹15,031 (400-pt ₹61,439 / −₹14,946 / −₹11,604). More margin. 2019–20 not run at 500-pt. Not adopted – user's call.
  FIVE-WAY COMPARISON incl. 500-pt (11-Oct-2026, NIFTY 2021–26, NSE closes, net; output/five_variant_comparison_500pt.xlsx; n / net / max DD /
  worst / PF / 0.5-pt slip). (1) no filter 300-pt 66 / ₹47,298 / −₹11,860 / −₹8,529 / 1.67 / ₹33,318. (2) ±2.5% 300-pt 45 / ₹66,052 / −₹7,527 /
  −₹7,243 / 3.20 / ₹56,492. (3) FINALISED §1b (±2%; 400-pt TP 60% if credit>=45%, 300-pt if 40–45%) 36 / ₹85,729 / −₹5,523 / −₹5,523 / 5.67 /
  ₹77,669. (4) ±2%, 500-pt TP 50% on ALL months with credit>=40% 36 / ₹110,219 / −₹9,515 / −₹9,515 (trade 30) / 4.68 / ₹102,159. (5) ±2%; 500-pt
  TP 60% if credit>=45%, 300-pt if 40–45% 36 / ₹100,287 / −₹5,523 / −₹5,523 / 6.47 / ₹92,227. Credit ratio = 400-pt condor's in all three.
  (4) vs (5): the 19 thin-credit months make ₹40,015 at 500-pt vs ₹26,668 at 300-pt (15 better), but the 4 losers grow: 30 −₹3,731 →
  −₹9,515 (stop-loss; fallback call strikes, credit only 142 pts), 67 −₹5,523 → −₹8,527, 22 −₹3,654 → −₹5,794, 55 −₹2,178 → −₹2,880. No losing
  year in 3, 4, 5. 500-pt max loss/condor ≈ 289 pts (≈ ₹18.8k at lot 65). 2019–20 not run at 500-pt. Nothing adopted – user's call.
  VARIANT 5 TWEAKS (11-Oct-2026; user prefers variant 5 = ±2%, 500-pt TP 60% if 400-pt credit>=45%, 300-pt if 40–45%: 36 tr ₹100,287 / DD −₹5,523;
  all from cached data; net / max DD) – NOTHING beats it at the same drawdown, do not re-test: target on the 500-pt trades 50% ₹96,872,
  60% ₹100,287, 70% or none ₹100,953 (all −₹5,523). Credit line for 500-pt: >=42/43% ₹109k / −₹8,527 (trade 67 goes to 500-pt); >=44% ₹97,444 /
  −₹5,794 + a losing year (trade 22); >=44.5% ₹99,585; >=46% ₹97,974; >=47% ₹92,533. Three tiers 500/400/300: 400-pt for 42–45% or 43–45% ₹103.5–104.3k /
  −₹6,976 + losing year; 400-pt for the whole 40–45% tier ₹108,973 / −₹6,976 + losing year. Move limit for the 500-pt trades: ±1.75% ₹95,268; ±2.25%
  ₹103,210 / −₹5,523 (adds trades 38 and 43, readings 2.01 and 2.05); ±2.5% ₹105,507 / −₹6,211 + losing year (15, 41). Floor 38–39% ₹101,146 (adds 45);
  41% ₹98,613; 42% ₹87,489. Plateau: credit line 44.5–46%, move limit 2–2.25%. Untested (needs downloads): 600-pt on the 17 rich months
  (349 calls; all 67 months 1,259), 500-pt in 2019–20. Sizing (2 lots in rich months) is the user's call, not a filter.
  600-PT HEDGES ON THE 17 RICH-CREDIT MONTHS (11-Oct-2026, NIFTY; only those 17 months downloaded at 600-pt; output/
  nifty_hedge_400_500_600_rich_credit_trades.xlsx; net / max DD / targets; TP 50% | TP 60%): 400-pt ₹55,646 | ₹59,061 / −₹1,558; 500-pt ₹70,204 |
  ₹73,619 / −₹1,815; 600-pt ₹84,392 | ₹88,271 / −₹2,045 (7 | 4 targets, 0 stops, win 88%). Each extra 100 pts adds ≈ ₹14.6k on these months
  (600 beats 500 on 16 of 17; trade 42 −₹1,815 → −₹2,045). Credit 191.5 / 224.5 / 254.1 pts; MAX LOSS per condor 208.5 / 275.5 / 345.9 pts
  (≈ ₹13.6k / ₹17.9k / ₹22.5k at lot 65). Whole §1b-style rule with 600-pt on the rich months + 300-pt on the 40–45% months: 36 tr ₹114,939
  (TP 60%) / DD −₹5,523 / PF 7.23 (500-pt ₹100,287; 400-pt ₹85,729). Only 2 of 17 on fallback strikes (44, 53; call spread 50 pts closer);
  92 non-exact daily prices vs 69 at 500-pt. CAVEAT: the gain is linear in width because none of these 17 months had a real loss – the test
  cannot show the cost of a bad month; the wider the hedge the closer this is to a short strangle. Not adopted – user's call.
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
| `data/nifty_daily.csv not found` | Run `python fetch_index_nse.py --from 2020-08-17 --to <today>` (or `IC_TREND_FILTER=off`) |
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
