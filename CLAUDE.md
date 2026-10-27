# CLAUDE.md – project context for Claude Code

## What this project is
Backtest automation for a NIFTY monthly iron condor that was first backtested on StockMock.
The engine replays the same 67 trades (same entry dates, expiries and strikes as StockMock) on
real 1-minute option prices from the ICICI Direct Breeze API and reconciles every trade.
Owner: beginner-to-intermediate systematic options trader, ₹3–5L capital, conservative,
target ~1–1.5%/month, capital preservation first. Explain trading/code decisions plainly.

Full user documentation: README.md. All settings: `ic/config.py`.

## Strategy rules (do not change without the user's explicit request)
- Entry at 11:16 (close of the 1-min candle labelled 11:16); next-month expiry. Forward test: 43 DTE = the Monday six weeks
  before a Tuesday expiry (`ENTRY_DTE`, `EXPIRY_WEEKDAY` in config, set 4-Oct-2026 at the user's request; next trading day if a
  holiday). Backtest history was 42–45 DTE (Thursday expiries until Aug-2025). If NSE changes the expiry day, update both.
- Sell ~30-delta CE + PE (strikes from StockMock report), buy 300 pts further out on both sides
  (`HEDGE_WIDTH`; was 200 = StockMock; changed 27-Sep-2026 at the user's request)
- One combined check per day at 15:16 (close of candle labelled 15:16); no intraday monitoring
- Exit all 4 legs: SL if P&L <= -100% credit, else TP if P&L >= 50% credit, else time exit on
  the last trading day on/before expiry − 18 calendar days (was 15; changed 27-Sep-2026 at the
  user's request). StockMock reference used 15 DTE (`REF_EXIT_DTE`).
- 1 lot at each expiry's lot size (`config.LOT_SIZES`: 50 → 25 for Jun-2024..Jan-2025 expiries → 75 →
  65; 25 confirmed from NSE circulars 28-Sep-2026); no adjustment, re-entry
- Entry filter (adopted 28-Sep-2026 at the user's request): skip the month if |NIFTY 10-day move| >
  2.5% at the close before entry (`SKIP_IF_10D_MOVE_PCT`, `IC_TREND_FILTER=off` to disable). No other filters.
- Optional gap-up exit (built in 2-Oct-2026, OFF by default, `GAP_UP_EXIT_PCT` / `IC_GAP_UP_EXIT=1.0`): exit all
  legs at 15:16 on a day NIFTY opens >= 1% above the prior close (not the entry day). User's call to switch on.
- NOTE (user, 3-Oct-2026): a 1% gap-up is the early call-side warning – 5 of the 7 trades where NIFTY later closed
  above the bought call (all 7 losses) had a >= 1% gap-up first; with the gap-up exit max DD −₹7.5k → −₹5.5k and
  profit ₹66,052 → ₹68,023 (300-pt, filter). Late warning: NIFTY closing above the bought call (trades 30, 52 had no gap).

## Forward-test rule set (ADOPTED 10-Oct-2026; wide condor = 400-pt (VARIANT 3) since 18-Oct-2026, user's decision; README §1b; `FWD_*` in config)
Used by the forward-test skill only – `backtest.py` defaults stay the earlier rule above (300-pt, ±2.5%), kept as the comparison.
- Evening before entry: 10-day move (NSE official closes). At 11:16: net credit of the 400-pt condor (30Δ sold legs, hedges 400 pts
  out) = the credit test (`FWD_SIGNAL_WIDTH` = 400) and, when rich, also the trade.
- |move| <= 2% AND that credit >= 180 pts (45% of 400) → 400-pt IC (`FWD_WIDE_WIDTHS` = [400], "variant 3"), **target 60%** of credit.
- |move| <= 2% AND credit 160–180 pts (40–45%) → 300-pt IC, target 50%.
- else skip. **Minimum-credit floor:** no IC of any width when the 400-pt credit is below 160 pts.
- Stop 100% of credit, 15:16 daily check, 18-DTE time exit, 1 lot, fallback strikes – unchanged.
- NOTE: the earlier rule (300-pt IC whenever |move| <= 2.5%) is the SHADOW LOG – record every month what it would have done.
- USER DECISIONS: 11-Oct-2026 one ±2% limit for all widths (was ±1.5% for 300-pt); 12-Oct-2026 first "variant 5 and 6 in place of variant 3", then the same
  day "finalise version 6" → 600-pt only on rich months (500-pt can be logged again via FWD_WIDE_WIDTHS = [500, 600]). Do not re-open
  thresholds or widths unless the user asks.
  18-Oct-2026: user switched the wide condor back to 400-pt – rule of thumb "maximum loss 2–3% of the account" (400-pt ≈ ₹13.6k/lot =
  2.7% of ₹5L; 600-pt ≈ ₹22.5k = 4.5–7.5% of ₹3–5L). REVIEW the width after 6–12 months of forward testing (≈ Apr–Oct 2027).
- Backtest 2021–26 (NSE closes, same 36 months = 17 rich + 19 at 300-pt; net / DD / PF / 0.5-pt slip): 400-pt (variant 3) ₹85,729 /
  −₹5,523 / 5.67 / ₹77,669; 500-pt (variant 5) ₹100,287 / −₹5,523 / 6.47 / ₹92,227; 600-pt (variant 6) ₹114,939 / −₹5,523 / 7.23 / ₹106,879.
  Max possible loss on a rich-month trade at lot 65 ≈ ₹13.6k / ₹17.9k / ₹22.5k – never tested: no rich month lost more than ≈ ₹2k.
  2019–20 only run at 400-pt (4 tr +₹7,040). 2019–26 at 400-pt: 40 tr ₹92,768 / −₹5,523.
- SMALL PRINT (README §1b, keep in mind when quoting the numbers): trade 24 (Dec-2022, no Breeze data) would have been a 300-pt trade
  (move −0.09%, StockMock credit 177.7 pts = 44.4%, StockMock −₹1,925 gross) → 2022 a small losing year, DD ≈ −₹5.8k. Trade 35 (Nov-2023
  stop) is skipped at +2.01%; at 2.00% it is a 300-pt trade −₹7,243 → DD −₹7.4k. Trade 38 also 2.01% (harmless); 43 at 2.05% (winner
  missed); 4 and 31 in at 1.96%. Floor: trade 30 in at 40.05% (−₹3,731), 31 at 40.5%, 45 out at 39.6% (+₹859, odd hedge print). 45% line:
  53 at 45.7% (wide), 22 / 55 at 44.4 / 44.5% (300-pt, smaller losses). Trade 67 passes everything (move −0.07%, 43.6%). Thresholds
  fitted; ≈6 trades a year.
- Tools (18-Oct-2026): ic_tools.py `strikes` prices the 400-pt condor (credit test and trade) and the 300-pt condor; `check` uses
  the 60% target for any condor >= 400 pts wide; journal template has credit_400/500/600/300_pts.
- Oct-2026 cycle (entry Mon 12-Oct-2026, expiry Mon 23-Nov-2026): 10-day move −2.35% → forward-test rule SKIPS; the earlier
  rule would TRADE the 300-pt IC → shadow-log it (time exit Thu 5-Nov-2026).

## Key lessons (user asked 3-Oct-2026 to keep these as notes – do not re-test; full list in README §1a)
- Call side: once NIFTY closes above the bought call the trade loses – 7/7 (with filter 4/4). 1% gap-up is the early
  warning (5 of those 7). Gap-up exit: 300-pt ₹68,023 / −₹5,523; 400-pt ₹88,148 / −₹6,976.
- Put side: no rule separates losers from winners (sold put crossed → 20/28 still profit); put-side exits double the DD.
- 400-pt hedges = more profit with a bigger drawdown (₹83,114 / −₹9,814 vs ₹66,052 / −₹7,527); gap-up exit helps both.
- 2019–2020 (out-of-sample, 7-Oct-2026): the same rules LOST money – with filter −₹7,579 on 15 trades, max DD −₹18,795 (lot 75);
  no filter −₹34,106. Expect a drawdown near ₹19k per lot; 2021–26 (₹66,052 / −₹7,527) was a kinder period.
- When a test is finished, add its conclusion to README §1a/§7 so the user does not repeat it.

## Decisions already made (with the user)
- Price rule: exact-minute candle close. Fallback: last traded candle earlier that day
  (FFILL/STALE), then first candle after (AFTER), flagged in Data_Quality. Entry leg with no
  Breeze price → StockMock price (REF).
- Time exit rolls to the previous trading day when the exit-DTE date is a weekend/holiday
  (confirmed: trade 62 → 13-Mar-2026, trade 67 → 11-Sep-2026 because 14-Sep-2026 was a holiday).
- Diwali Muhurat sessions (`config.MUHURAT_DAYS`) are non-trading days for the strategy: no daily
  check, never a time-exit day. Add each new year's date when NSE announces it.
- 18 DTE chosen after tests (27-Sep-2026, 200-pt hedges, 67 trades): net ₹18.4k → ₹26.8k, net max DD −₹17.9k → −₹9.3k,
  1 condor at a time. Rejected: TP 40%, SL 50/75%, SL 50% + 18 DTE, TP 40% + SL 50%. No TP/SL/DTE
  value reduced the 18-DTE drawdown further. Result is sensitive (17 and 21 DTE worse) – paper trade.
- Cached candles: 200-pt legs cover entry → StockMock exit (~15 DTE); 300-pt hedges cover entry →
  max(18 DTE, StockMock exit). Earlier exits need no download.
- Final setup (27-Sep-2026): 300-pt hedges + 18 DTE + SL 100% + TP 50%. Net ₹38,581 on 61 trades,
  net max DD −₹11,860, largest loss −₹8,529 (200-pt, same trades: ₹23,108 / −₹9,286 / −₹5,834).
  Rejected for 300: SL 50/60/75/80%, exit DTE 15–17 and 21–30. Both widths best at 18–20 DTE.
- `HEDGE_WIDTH` (env `IC_HEDGE_WIDTH`, default 300; `REF_HEDGE_WIDTH` = 200 StockMock) moves both
  bought legs; 200 and 300 are cached, other widths need their own download.
- With 300-pt hedges trades 1, 24, 29, 30, 31, 33, 57 had no usable price at entry; the fallback rule now
  moves them to the nearest priced strikes (24 still has no data).
- Slippage is the biggest sensitivity: 1 pt/leg → 300-pt ≈ ₹11k net, 200-pt negative.
- Trade 23 was exited manually in StockMock → expected reconciliation mismatch.
- April-2026 cycle is not traded (StockMock had no data).
- Trade 9 (Sep-2021) has thin data – judge it using Data_Quality.
- NIFTY daily close for the 10-day filter = NSE's OFFICIAL close (last-30-minute average), from NSE's daily index file
  (archives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv, "Nifty 50" / "Closing Index Value") – backtest file
  data/nifty_daily.csv via `fetch_index_nse.py`, forward test via ic_tools.py (same file, read live). Switched from Breeze daily
  candles (last traded value) on 11-Oct-2026 after the user's cross-check; `download.py --index` only fills missing days.
- Option-price data source: ICICI Breeze (free, exact strike+expiry, 1-min). Probe run confirmed coverage
  2022–2026 fully, 2021 mostly; prices within a few tenths of StockMock; net credit within ~1.5 pts.
- Costs modelled approximately in `config.COSTS` (~₹250 per condor); report gross and net.

## Layout
- Entry scripts in root: `login_url.py`, `probe.py`, `download.py`, `backtest.py`, `select_strikes.py`, `export_prices.py`, `make_trades.py`, `fetch_index_nse.py`
- Code in `ic/` (index-aware via `config.INDEX`): `config.py`, `breeze_client.py`, `common.py`, `downloader.py`, `engine.py`, `export.py`, `fallback.py`, `probe.py`, `strikes.py`, `cli.py`, `tradeset.py`, `nse_index.py`
- Reference data (committed): `data/reference/ic_reference_trades.csv`, `ic_reference_legs.csv`,
  `stockmock_export.xlsx`; validation workbook in `docs/`
- Generated (git-ignored): `data/cache/` (1-min candles), `data/nifty_trading_days.csv`, `output/`

## Second index: BANKNIFTY (engine made index-aware 11-Oct-2026 at the user's request; README §5.3e)
- `--symbol banknifty` on any script (= `IC_INDEX=BANKNIFTY`); default NIFTY. Per-index values live in `INDEXES` in `ic/config.py`
  (breeze code, strike step, default hedge width, fallback shifts, lot sizes, expiry weekdays). Rules are shared.
- NIFTY must stay byte-identical: checked 11-Oct-2026 (main report, 2019–20 set, 400-pt no-filter, leg prices, make_trades output
  all identical before/after). Re-run that comparison after any further change to shared code.
- BANKNIFTY files: `data/reference/banknifty_ic_reference_trades.csv` / `_legs.csv`, `banknifty_ic_trades_<set>.csv`,
  `data/strike_sets/banknifty/`, cache `BANKNIFTY_<expiry>_<strike>`, `data/banknifty_daily.csv` (NSE official closes, "Nifty Bank"),
  reports `output/BANKNIFTY_IC_backtest_*.xlsx`. Calendar, Muhurat days, costs shared.
- StockMock BANKNIFTY report validated 11-Oct-2026 (data/reference/Banknifty IC backtesting_StockMock.xlsx → the two
  banknifty_ic_reference_*.csv): 67 trades (same months as NIFTY), 30Δ, 500-pt hedges, TP 50%, 18-DTE exit; gross ₹25,894, worst
  −₹10,836 (trade 62, −154% of credit on the time-exit day), 41 W / 26 L. 58 time / 5 target (6, 29, 39, 49, 54). Three exits one
  trading day early (24, 41, 42 → MANUAL). Hedges 600 on trades 58 (CE) and 61 (both). Entry differs from NIFTY only for trade 42
  (18-Jun-2024). Lots: StockMock 25 for Jul/Aug-2023 expiries (30, 31) vs NSE 15 (circular FAOP56233) – engine uses 15
  (StockMock total at engine lots ₹24,690). Config set from it: hedge_width 500, ref_exit_dte 18; expiry weekdays confirmed.
- data/banknifty_daily.csv fetched 11-Oct-2026 (NSE official, 1-Oct-2018..9-Oct-2026, 1,987 days = same dates as nifty_daily.csv).
  fetch_index_nse.py skips weekends, so the 7 special weekend sessions were added by hand with ic.nse_index.fetch_day – repeat for
  any new index. make_trades --symbol banknifty reproduces all 67 entry and expiry dates of the report.
- PREVIEW ONLY (StockMock P&L at engine lots, BANKNIFTY's own 10-day move; not an engine result): no filter 67 tr ₹24,690 / DD −₹10,836;
  ±2.5% 37 tr ₹23,031 / −₹6,080; ±2% 28 tr ₹30,130 / −₹5,277; ±3% 46 tr ₹18,848 / −₹9,406. Trade 62 reads +3.03% (skipped at 2.5 and 3).
- Probe 11-Oct-2026 (trades 1, 9, 20, 35, 48, 56, 62, 67): `CNXBAN` CONFIRMED, data 64/64, all years; exact-minute candle missing
  in 13 checks (2021–22 thin: trade 1 had 5 candles before 11:16, trade 9 sold CE stale 41 min); last-traded fallback within 2% of
  StockMock in 59/64; largest diffs ≈ 8–11 pts on 500–3,000-pt premiums (trade 48 both PE legs −9.75, cancels in the spread). Download ≈ 2,608 calls (`download.py --symbol banknifty`) – needs the user's session.
- FIRST BANKNIFTY BACKTEST 11-Oct-2026 (download complete; 30Δ, 500-pt, TP 50%, SL 100%, 18 DTE; README §5.3e; n / gross / net / net DD /
  PF net): no filter 67 / ₹26,060 / ₹8,291 / −₹12,043 / 1.13; ±2.5% 37 / ₹21,185 / ₹11,709 / −₹12,256 / 1.39; ±2% 28 / ₹28,456 / ₹21,373 /
  −₹9,774 / 2.15; ±1.5% 20 / ₹31,131 / ₹26,124 / −₹6,439 / 3.84; ±3% 46 / ₹4,806 net / −₹15,892. By year (±2.5%, net): 2021 +4.1k, 2022 −5.1k,
  2023 +6.6k, 2024 −2.9k, 2025 +2.6k, 2026 +6.5k. Engine vs StockMock (67, no filter): gross ₹26,060 vs ₹24,690; 36 within 3 pts, 55 within 10;
  same exit 61/67. Costs ≈ ₹265/condor = ₹17.8k of ₹26.1k gross (small lot 15–35, big premiums). Credit avg 262 pts = 52% of width → max
  loss ≈ 93% of credit, so the 100% stop is unreachable in 45/67 trades; only 6 targets → effectively a time-exit-only trade.
  The 2 engine stop-losses are BAD PRINTS: trade 37 (29-Jan-2024, condor value 557 > 500 width; stale deep-ITM 47200PE) and 62
  (9-Mar-2026, 517); StockMock's −361 pts on 62 is also beyond max loss. Trade 37 at its time exit: no filter ₹11,423 net; ±2.5% ₹14,841 /
  −₹9,124. NIFTY runs have 0 days with value > width. PROPOSED (not built, user to decide): sanity rule "condor value above its
  hedge width = bad print → skip that daily check". 432 of 487 non-exact prices are 2021–22. Versus NIFTY 300-pt ±2.5% (₹66,052 /
  −₹7,527) BANKNIFTY earns about a fifth with a larger drawdown under the same rules.
- BANKNIFTY 600-PT HEDGES (12-Oct-2026, output/BANKNIFTY_IC_backtest_sm_h600_nofilter.xlsx): NOT A USABLE TEST – the hedge strikes do not trade.
  Far BANKNIFTY strikes six weeks out trade on round 500s; 75% of the sold strikes are on a round 500, so a 600-pt hedge lands on an odd
  hundred (e.g. 34600). Result: 23 of 67 trades had no hedge price at entry and did not run, 17 of the 44 that ran used fallback strikes,
  699 non-exact prices (244 stale > 15 min), and 14 of the 44 show an impossible credit (a wider hedge must collect more than the 500-pt
  condor: 8 collect less, 6 collect 1.5–2.5× as much, e.g. trade 41 credit 637 pts on a 600-pt width). Headline (unreliable): 44 tr net
  −₹8,791 / DD −₹23,334 no filter; ±2.5% 25 tr −₹3,317; the same 44 trades at 500-pt −₹8,159. Only 19 trades are clean (plausible credit, no
  fallback): 600-pt −₹21,355 vs 500-pt −₹19,246, 600 better on 8 – no sign that the wider hedge helps. Do NOT download 700-pt (same odd-strike
  problem). The testable wider hedge is 1,000 pts (lands on round 500s like the 500-pt run, which had 0 trades not run and 1 fallback).
- BANKNIFTY 1,000-PT HEDGES (12-Oct-2026, output/BANKNIFTY_IC_backtest_sm_h1000_nofilter.xlsx; 30Δ, TP 50%, SL 100%, 18 DTE; n / gross / net / net DD /
  worst / PF): data usable – 62 of 67 ran (2, 4, 24, 57, 66 no hedge price), 9 on fallback strikes, 0 days with value > width, credit 1.76× the
  500-pt credit (2 odd: 40 at 1.13×, 64 at 2.28×). No filter 62 / ₹48,358 / ₹32,471 / −₹18,505 / −₹14,421 (trade 62) / 1.35; ±3% 42 / ₹23,237 net /
  −₹21,610; ±2.5% 34 / ₹44,008 / ₹35,593 / −₹13,944 / −₹7,025 / 1.93; ±2% 26 / ₹51,983 / ₹45,623 / −₹10,171 / −₹6,746 / 2.86; ±1.5% 19 / ₹52,204 net /
  −₹3,993 / PF 7.10. Same 62 trades at 500-pt: ₹5,928 net → the wider hedge DOES lift profit (user's idea confirmed; 1,000 better on 42 of 62).
  Why: credit 457 pts = 46% of width (500-pt: 52%), so stop and target work again – 8 targets, 3 real stops at −105% (35, 48, 62);
  costs ≈ ₹256/condor are now 33% of gross instead of 68%. Cost of it: losses double (62 −₹8.9k → −₹14.4k; 48, 19, 35, 51, 16 each −₹3.5k →
  ≈ −₹7k), max loss/condor 543 pts ≈ ₹16.3k at lot 30. By year ±2.5%: 2021 +8.6k, 2022 −8.8k, 2023 +14.1k, 2024 +3.2k, 2025 +10.8k, 2026 +7.7k.
  0.5-pt slip ±2.5% ₹32,473. Versus NIFTY 300-pt ±2.5% (₹66,052 / −₹7,527): about half the profit with nearly twice the drawdown; 174+170
  of the 418 non-exact prices are 2021–22. ±1.5%/±2% look best but were picked after seeing the data (3–4 trades a year). Not adopted.
- BANKNIFTY AS AN ALTERNATIVE IN NIFTY'S SKIPPED MONTHS (12-Oct-2026, user question) – NO. The two filters pick mostly the same months: 10-day
  moves correlate 0.81; at ±2.5% NIFTY passes 45 of 67, BANKNIFTY 36, both 32, NIFTY only 13, BANKNIFTY only 4 (23, 24, 33, 52), neither 17
  (at ±2%: 37 / 27 / both 21 / NIFTY only 16 / BANKNIFTY only 6). The 3 BANKNIFTY-only months with data made −₹3,483 at 1,000-pt (52 −₹3,401).
  Months the finalised NIFTY rule skips but BANKNIFTY ±2.5% passes: 11 tr −₹2,212. Trade P&L correlation NIFTY 300-pt vs BANKNIFTY 1,000-pt
  0.61 (62 months, no filter); both lose in 15 of NIFTY's 24 losing months; 7 of NIFTY's 10 worst months lose on BANKNIFTY too (62, 35, 19,
  16, 52, 22, 15); exceptions 67, 8, 30. Running both (each with its own ±2.5% filter): ₹101,644 / DD −₹17,607 (NIFTY ₹66,052 / −₹7,527 +
  BANKNIFTY ₹35,593 / −₹13,944); finalised NIFTY rule (400-pt) + BANKNIFTY ₹121,321 / −₹11,126. BANKNIFTY adds size, not diversification.
- The `FWD_*` forward-test rule and the skill are NIFTY only. Do not apply NIFTY-fitted thresholds to BANKNIFTY without a test.

## Commands
```bash
source .venv/bin/activate
python tests/smoke_test.py      # offline end-to-end test (fake Breeze) – run after code changes
python login_url.py             # daily Breeze login URL
python probe.py [--trades ..]   # data availability check (API)
python download.py              # fetch candles (API, restart-safe, ~3,100 calls)
python fetch_index_nse.py --from YYYY-MM-DD --to YYYY-MM-DD [--replace]   # NIFTY + VIX OFFICIAL daily closes from NSE (no login)
python download.py --index      # Breeze daily OHLC – only fills days the files lack (not the official close)
python select_strikes.py --ce-delta 0.25 --name ce25   # delta-based sold strikes (API) -> IC_STRIKE_SET=ce25
python backtest.py [--trades ..] [--out path]   # offline, writes output/IC_backtest_report.xlsx
# variant options on download.py / backtest.py / export_prices.py (ic/cli.py -> IC_STRIKE_SET / IC_HEDGE_WIDTH / IC_TREND_FILTER):
python select_strikes.py --ce-delta 0.10 --pe-delta 0.10 --around 3 --step 100 --name d10 [--dry-run]   # API, few calls
python download.py --strike-set d10 --hedge 500 [--dry-run]     # --dry-run: count calls only, no login
python backtest.py --strike-set d10 --hedge 500 --filter off    # -> output/IC_backtest_d10_h500_nofilter.xlsx
python export_prices.py [--trades ..] [--out path] # offline, daily leg prices -> output/IC_leg_prices.xlsx
```

## Rules for working in this repo
- NEVER read, print, edit or commit `.env`; never echo API keys, secrets or session tokens.
- NEVER place, modify or cancel orders. This project only reads historical data; do not add
  order-placement code unless the user explicitly asks, and even then ask before running it.
- Breeze limits: 100 calls/min, 5,000/day. Don't run `download.py`/`probe.py` casually –
  ask the user first (it needs today's session token and uses quota).
- Keep all tunable values in `ic/config.py`; keep the root scripts as thin entry points.
- Run `python tests/smoke_test.py` after any change to `ic/`; update README.md when behaviour,
  commands or settings change.
- Small, reviewable commits with clear messages; don't rewrite git history.

## Current status / next steps
Done: data downloaded (200 + 300-pt hedges, NIFTY/VIX daily), rule variations tested, final setup
chosen (300-pt hedges, 18 DTE, SL 100%, TP 50%; net ₹38,322 on 60 trades, max DD −₹11,860), lot sizes
corrected, 15-DTE StockMock manual run reconciled (output/reconcile_manual300_vs_engine.xlsx).
Price sanity rules (28-Sep-2026): entry prices from trades >15 min after 11:16 rejected; a hedge priced
>= its sold leg is a bad print (skip trade at entry / skip that daily check). This dropped trade 29.
10-day trend filter ADOPTED and in the engine (28-Sep-2026): main report = 42 trades, net ₹64,859,
max DD −₹7,243, win 74%, PF 3.46; 21 months skipped (Skipped sheet). Study: output/trend_filter_study.xlsx.
Threshold re-test 1-Oct-2026 (current data, no-filter 66 trades ₹47.3k / DD −₹11.9k): ±1.5 ₹56.6k/−5.5k (27 tr),
±2.0 ₹59.0k/−9.9k, ±2.5 ₹66.1k/−7.5k, ±3 ₹58.3k/−8.5k, ±4 ₹47.9k/−14.7k, ±5 ₹47.5k/−13.9k. CAVEAT: 2021–23
alone picks ±3% (not 2.5), and ±3% ≈ no gain on 2024–26 (₹41.5k vs ₹41.2k); ±2.5 wins 2024–26 because trades
48/52/62 sit between 2.5–3%. Filter idea robust across 1.5–3.5% on the full period; exact 2.5 is partly
fitted – expect a smaller benefit live. Down-move limit: only 3 trades, no evidence (up≤2.5/down≥−2 +₹1.2k).
Tested on top of it, not adopted: VIX level/change, VIX − realised vol (failed 2024–26), 50/200-DMA,
5/20-day moves, range, credit size. Event filters tested 29-Sep-2026 (holding through the event date):
India election results alone skip 7 trades (2 losers/5 winners, ≈ ₹0, DD worse) – no use as a primary
filter; on top of ±2.5% +₹3.9k (all from trade 35) – judgement rule only. Union Budget months were all
winners (6/6 BT, 7/7 SM; skipping costs ≈ ₹18k) – do NOT avoid budgets. US election 2024 = trade 46,
already skipped by ±2.5%.
Tested 28-Sep-2026, not adopted: 30Δ put + 25Δ call (IC_STRIKE_SET=ce25; data/strike_sets/strikes_ce25.csv).
Mixed: +₹5.0k on the 55 common trades (helps 2021/23/24 rallies, hurts 2025–26) but 5 months had
no clean far-call price; full-set ₹36,593 vs ₹38,322 (with filter ₹56,250 vs ₹64,859).
Tested 29-Sep-2026, not adopted: trade the filter months with strikes shifted with the trend
(select_strikes.py --trend-shift; strike sets shiftA = 20Δ trend-side leg, shiftB = 20Δ trend side + 35Δ
other side; output/trend_shift_test.xlsx). Those months stay losing (normal −₹26.5k, A −₹27.2k, B −₹24.5k);
full strategy A ₹37.7k / DD −₹13.2k, B ₹40.4k / DD −₹12.8k vs skipping ₹64.9k / −₹7.2k. Cause: shifting
cuts the credit, so reversals hit the 100%-of-credit stop sooner (trade 50: −₹2.4k → −₹9.8k/−₹10.4k).
Gap-exit rule tested 1-Oct-2026, not adopted (exit all legs on a day NIFTY opens with |gap| >= G vs prior
close; at 15:16 or 09:20; optionally only if losing). Without the trend filter gap>=1.25% @15:16 helps
(₹47.3k/−11.9k → ₹54.7k/−9.9k; trade 62 −₹8.5k → −₹0.9k). With the adopted ±2.5% filter every variant cuts
profit (₹66.1k → ₹55–64.5k): 10 of 14 gap exits were trades that recovered; only gap>=1% lowers DD
(−7.5k → −6.1k) at −₹11k. Trade 62 is already skipped by the filter.
Entry filter + gap exit (gap>=1.25% @15:16) combos: ±3% ₹64.7k/−7.7k (52 tr); ±4% ₹64.5k/−7.7k; up>+4% only
₹62.8k/−7.7k; down<−2.5% or (up>+4% & VIX<15) ₹70.1k/−7.7k (60 tr) vs base ±2.5% ₹66.1k/−7.5k. Gap level is
very sensitive (1.0/1.5% much worse for most); combos win 2021–23, base wins 2024–26; with 0.5–1 pt/leg
slippage base is equal/best. Kept base ±2.5% (1 parameter vs 3–4).
400-pt hedges tested 2-Oct-2026 (IC_HEDGE_WIDTH=400, downloaded; output/IC_backtest_hedge400.xlsx,
output/hedge300_vs_400_trades.xlsx). With ±2.5% filter: 44 trades ₹83,114 / DD −₹9,814 / worst −₹9,814 /
win 75% / PF 3.17 vs 300-pt ₹66,052 / −₹7,527 / −₹7,243 / 73% / 3.20. Credit 181 vs 146, max loss/condor
219 vs 154 pts; better in 5 of 6 years (2022 worse). 0.5 pt slip: ₹73.8k vs ₹56.5k. Not adopted yet –
user's decision (more margin and bigger worst case); default stays 300.
Gap-UP exit tested 2-Oct-2026 (user idea; exit all legs at 15:16 on a day NIFTY opens >= G% above the prior
close). With ±2.5% filter: 300-pt G=1.0% ₹68,023 / DD −₹5,523 (base ₹66,052 / −₹7,527); 400-pt ₹88,148 / −₹6,976
(base ₹83,114 / −₹9,814). Every year positive (2022 −₹3.3k → +₹1.5k). G=1.25/1.5 also ≥ base on profit but DD only
−7.2k; G=0.75 much worse. Helps 2021–23 (₹14.2k→₹21.3k, DD −7.5k→−3.7k), slightly hurts 2024–26 (₹51.8k→₹46.7k).
Key trades 35 (+₹6.3k), 22, 15; 10 small winners trimmed. Gap-DOWN exits are harmful (DD −12k to −16k).
Built into the engine as an optional rule, OFF by default (engine reproduces the test exactly).
Gap-up level by period (4-Oct-2026, 300-pt, filter; 2021–23 / 2024–26): base ₹14.2k / ₹51.8k; 1% ₹21.3k / ₹46.7k; 1.25%
₹19.3k / ₹49.8k; 1.5% ₹19.2k / ₹49.6k. 1% costs 2024–26 ₹5.2k via trades 56 (gap 1.03%, −₹2.8k), 61 (4.69%, −₹1.9k), 43, 41;
1.25% saves only 56 and 43. No 2024–26 loss avoided at any level. 1.25/1.5% lose the DD cut (trade 35: 1.09% gap 15-Nov-23
→ −₹897; next gap 1.71% on 4-Dec → −₹6,933). 1% vs 1.25% hinges on trades 35 vs 56/3 – do not tune further; keep 1%.
Asymmetric hedges tested 2-Oct-2026, not adopted (IC_HEDGE_WIDTH_CE/PE): with ±2.5% filter CE300/PE400
₹72,533 / DD −₹10,935, CE400/PE300 ₹70,920 / −₹11,123 vs 300/300 ₹66,052 / −₹7,527 and 400/400 ₹83,114 / −₹9,814.
Wide side adds ~100 pts risk for ~17 pts credit (max loss ≈237 pts > 400/400's 219); trade 11 −₹635 → SL −₹8,584.
Close-one-side rule tested 2-Oct-2026, not adopted: close the call or put spread when it alone loses >= X% of
total credit. 300-pt with filter: X=40–100% gives ₹16.8k–₹57.7k (vs ₹66.1k) and DD −₹9.0k to −₹16.0k (vs −₹7.5k);
tested side usually recovers, remaining side gets hit on the reversal (60%: 6 helped +₹11.3k, 11 hurt −₹45.3k).
Lock-in-profit tested 2-Oct-2026, not adopted: fixed floor (arm A%, exit at B%) and trailing (T% below peak).
Max DD unchanged in every variant (−₹7,527 / −₹9,814). Best 300-pt arm 25%/floor 5% ₹73,722 (+₹7.7k, 5 exits,
mostly trade 67); neighbours mixed (arm 20/floor 10 ₹59.4k, arm 30/floor 10 ₹63.2k). Too few exits to trust.
Entry-day test set up 2-Oct-2026 (IC_ENTRY_SHIFT=2 Wed; Friday changed at user's request to the PREVIOUS Friday:
IC_ENTRY_SHIFT=-3 IC_ENTRY_TIME=15:16, 48/46 DTE, strike set d30_fri – roll: exit old + enter new at 15:16;
38/66 entries fall on the previous trade's exit Friday, 20 a week later, never overlapping; strike sets d30_s0/d30_s2/d30_s4 = ~30Δ CE+PE
chosen on that day by select_strikes.py --ce-delta 0.30 --pe-delta 0.30 --range 200 --closer 4). Entries were
Monday for 65/67 trades; only trades from Sep-2025 (12) had Tuesday weekly expiries (Thursday before).
Entry-day results (2-Oct-2026, all strikes ~30Δ after widening the search for 6 trades per test): Monday SM
₹66,052/−₹7,527; Monday 30Δ ₹65,171/−₹8,026 (validates strike method); Wednesday ₹27,653/−₹16,280; previous-
Friday 15:16 roll ₹52,881/−₹11,179. Sep-2025+ Tuesday-expiry period: Monday still best. Keep Monday 11:16.
Friday roll with the 10-day move on live 15:16 NIFTY (not prior close): ₹64,015 / −₹7,458 ≈ Monday; the weak 2025–26
was mainly the filter missing Friday's move (trades 50, 62).
No filter: Monday 30Δ ₹45,814/−₹11,488 vs Friday roll ₹36,464/−₹12,011 (Friday better 2021–24, worse 2025–26).
Filter + gap-up 1%: Monday 30Δ ₹65,679/−₹5,550 vs Friday roll ₹51,225/−₹7,458 (weekend gap-ups exit Friday trades on day 1).
CE/PE split filter (3-Oct-2026): with trade 62, CE2.5/PE2.5 best (₹66,052/−₹7,527); CE3/PE2.5 ₹62,516/−₹8,529. Without
trade 62 (hindsight) CE3/PE2.5 ₹71,045/−₹7,243 wins both periods (SM ₹67,407). Fair version – gap rule on ALL trades:
gap-up 1%: CE2.5/PE2.5 ₹68,023/−₹5,523 vs CE3/PE2.5 ₹68,159/−₹5,523 (equal, 6 more trades); gap up-or-down 1%: CE3/PE2.5
₹57,045/−₹8,993 (worse). PE-side limit only touches 3 trades (17, 46, 52). Kept 2.5/2.5.
Up-limit ladder (PE 2.5%): no gap exit 2.5% ₹66,052/−₹7,527, 3% ₹62,516/−₹8,529, 3.5% ₹56,678/−₹10,057; with gap-up 1%:
₹68,023 / ₹68,159 / ₹67,665, all −₹5,523 (PF 4.88 / 3.64 / 3.28). Looser up-limits only work WITH the gap-up exit.
Skipped months split (4-Oct-2026, 300-pt, output/filter_skipped_trades_CE_PE.xlsx): after a rise > 2.5% – 18 trades, 8 profit /
10 loss, −₹15,061: 6 lost on the call side as the rally continued (8, 19, 36, 9, 5, 28 = −₹17.3k), 4 on the put side on a
reversal (62, 16, 48, 50 = −₹18.0k). After a fall > 2.5% – 3 trades (17 +₹2,056, 46 −₹1,570, 52 −₹4,180), −₹3,694. No SL exits.
Skipped months – 10-day move on the next 10 trading days (4-Oct-2026, output/skipped_trades_next_10day_move.xlsx): the reading is
back inside ±2.5% after 1 day in 8 of 21, within 3 days in 13, within 8 days in all (median 2); average after a rise 3.75% →
1.57% (day 5) → −0.33% (day 10). But it often leaves the band again (16, 48, 50 to the down side; 5, 19, 63 back up), and the 4
reversal losers (62, 16, 48, 50) were all back inside within 1–2 days – "enter as soon as it is back inside" would re-take them.
Hedge width with ±2.5% filter (3-Oct-2026, output/IC_backtest_hedge200.xlsx): 200-pt ₹41,596 / DD −₹5,127 / worst −₹4,695 /
max loss ≈96 pts; 300-pt ₹66,052 / −₹7,527 / −₹7,243 / 154 pts; 400-pt ₹83,114 / −₹9,814 / −₹9,814 / 219 pts. Profit÷DD ≈ 8–9
for all three; 0.5-pt slippage: 200 ₹31.8k, 300 ₹56.5k, 400 ₹73.8k.
Strike-cross study (3-Oct-2026, 300-pt, 66 trades): CE hedge crossed → 7/7 losses; CE sold crossed → 15/20 losses; PE sold
crossed → 20/28 profits; PE hedge crossed → 8/16 profits. Call-side exit at NIFTY close >= bought CE (with filter):
₹66,879 / DD −₹5,997 / worst −₹5,523 (base ₹66,052 / −₹7,527); exit at sold CE costs ≈₹12k; PE-side exits double the DD.
Candidate adjustment (not adopted): exit when NIFTY closes above the CE hedge.
PE hedge crossed split by filter (4-Oct-2026): traded months 9 → 6 profit / 3 loss, +₹1,838 (67, 55, 11 lost); skipped months
7 → 2 / 5, −₹16,500. Loss only when NIFTY is still below the bought put at exit (7 of 7; 8 of 9 that recovered made a profit); no early signal.
Built in as optional `CE_BREACH_EXIT_PTS` / `IC_CE_BREACH_EXIT=hedge` (off by default). Combination test: 300-pt + filter –
gap-up ₹68,023/−₹5,523; CE cross ₹66,898/−₹6,018; both ₹67,989/−₹5,523 (CE cross redundant once gap-up is on; fires once,
trade 30). 400-pt: gap-up ₹88,148/−₹6,976; CE cross alone ₹81,190/−₹9,814; both = gap-up. Gap-up remains the one useful exit.
Summary web page: https://claude.ai/artifact/SHyqgqYkgyeEAg4FkPVwqm (republish on changes; shared by the user as "anyone with the link";
last republished 18-Oct-2026 with the 400-pt forward-test rule and the 400 vs 600 risk/reward table; source kept in docs/summary_page.html –
edit that file and publish it with the artifact url).
18-DTE StockMock manual run (data/reference/Iron condor sell 30delta and buy 300 points hedge with
18DTE exit_StockMock.xlsx) validated 28-Sep-2026 (output/manual18_data_check.xlsx,
output/reconcile_manual18_vs_backtest.xlsx): times, expiries, lot sizes, arithmetic all correct; trade 35
was closed manually on 4-Dec (rule exit = SL 5-Dec, corrected using Breeze 5-Dec prices). 59 same-strike
trades: 48 within 3 pts, 55 same exit; mismatches = borderline 50% targets (StockMock/Breeze within
<1 pt of the line) and thin 300-pt hedge prices. StockMock 67 trades ≈ ₹42.7k net (approx costs),
MDD −₹12.9k; with 10-day filter ≈ ₹64.2k, MDD −₹7.2k (backtest ₹64.9k / −₹7.2k) – filter confirmed.
Extra Apr-2026 cycle traded in StockMock (entry 16-Mar-26, PE hedge 400 pts) – not in the backtest.
Fallback rule used by the user when a strike has no price: nearest strike with a price, sold leg kept
near 30 delta (prefer 100 pts closer); hedge 300 pts, else next available (e.g. 400).

Variant workflow built 5-Oct-2026 (README §5.3c): any sold delta (select_strikes.py --around = search around a Black-Scholes
estimate, ~750 calls for 10Δ on all trades vs ~4,100) + any hedge width (--hedge). All three variant tests below are done.
40Δ sold legs tested 5-Oct-2026, NOT adopted (strike set d40, all 66 trades; output/IC_backtest_d40_h300[_nofilter].xlsx,
IC_backtest_d40_h200[_nofilter].xlsx). With the ±2.5% filter, same 45 trades (net / max DD / win / PF): 30Δ+300 ₹66,052 / −₹7,527 /
73% / 3.20; 40Δ+300 ₹43,912 / −₹6,186 / 69% / 2.64; 40Δ+200 ₹23,838 / −₹5,585 / 64% / 2.16 (30Δ+200 ₹42,911 / −₹4,695). No filter:
40Δ+300 ₹23,673 / −₹12,171; 40Δ+200 −₹1,699 / −₹19,423 (30Δ+300 ₹47,298 / −₹11,860). 0.5-pt slippage: 40Δ+300 ₹34.4k, 40Δ+200 ₹14.3k.
Why: credit is 203 of 300 pts (141 of 200), so the 50% target (≈100 pts) was never reached – 0 targets vs 11 – and the 100% stop
is beyond the maximum loss, so it cannot trigger; every trade is a time exit. Worse in every year. TP/SL as % of credit do not
fit 40Δ; a fair retest would need its own TP/SL (not done).
Delayed entry for skipped months tested 5-Oct-2026, NOT adopted (re-check the filter the next Monday, enter a fresh 30Δ/300-pt
IC at 35–38 DTE if inside ±2.5%; strike set d30_nm, --entry-shift 7): 13 of 21 months qualify; 12 run (trade 20 not downloaded):
5 profit / 7 loss, net −₹22,988 (same months at the original entry −₹19,742; skipping = ₹0). 3 stop-losses (62 −₹11.4k,
12 −₹6.8k, 8 −₹6.5k); helped 50, 9, 16, hurt 12, 5, 62. A calm reading one week later does not make these months safe.
Exit-DTE ladder WITH the ±2.5% filter (5-Oct-2026, 300-pt, 45 trades; net / max DD): 17 ₹64,819 / −₹11,416; 18 ₹66,052 / −₹7,527;
19 ₹62,376 / −₹7,527; 20 ₹58,490 / −₹7,527; 21 ₹52,829 / −₹7,243; 22 ₹43,972 / −₹7,243; 23 ₹37,508 / −₹9,880; 25 ₹34,074 / −₹7,332.
The popular "exit at 21 DTE" costs ₹13.2k for no drawdown gain: for Thursday expiries 18 DTE already means Friday = 20 DTE, and
21 DTE is one day earlier (Thursday); for Tuesday expiries it is 3 trading days earlier. Fewer targets reached (11 → 4). Keep 18.
"45 DTE entry" = what the backtest did with Thursday expiries (Monday = 45 DTE); 43 DTE is the same Monday for Tuesday expiries.
Calendar bug fixed 5-Oct-2026: download.py --trades rebuilt data/nifty_trading_days.csv from the first selected trade, dropping
earlier days (then treated as holidays). build_calendar now merges with the existing file. Breeze daily data has gaps: calendar
lacked 18-Dec-2025, nifty_daily.csv lacked 1-Feb-2023 and 21-Jul-2025 (patched from NSE; trade 26 reading −0.27% → +1.36%, no
decision changed). Trade 60's 18-Dec-2025 candles downloaded 5-Oct-2026: main report unchanged
(45 trades / ₹66,052 / −₹7,527).
10Δ + 500-pt hedges in the filter-skipped months (5-Oct-2026, strike set d10, output/IC_backtest_d10_h500_nofilter.xlsx), NOT
adopted: only 11 of 21 months could be run – in the other 10 the call hedge 500 pts beyond the 10Δ call had no price at 11:16
(strikes 300+ pts beyond a 10Δ call mostly do not trade 6 weeks out; puts are fine). The 11 that ran: 5 target / 6 stop-loss,
net −₹15,235 vs −₹9,185 for the 30Δ/300-pt condor on the same months. Credit only ≈50 pts (30Δ ≈141), so the 100% stop sits
close: stops at 1.0–1.7× credit (−₹1.5k to −₹4.9k) against ≈₹1–1.8k per win. Not an alternative for skipped months.
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
User leaned towards the two-tier rule on 7-Oct-2026, then discarded it on 8-Oct-2026 (see below).
Trade 60's 18-Dec-2025 candles for the 200 and 400-pt hedges were downloaded 7-Oct-2026; 400-pt results unchanged (₹83,114).
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
Forward-test tools updated 10-Oct-2026: ic_tools.py `rules` prints the FWD rule set; `filter` gives the FWD verdict (trade / trade
only if rich / skip) plus the earlier rule's; `strikes` prices the 400-pt and 300-pt condors, decides the width from the 400-pt
credit and the 10-day move (or --move), shows target 60%/50%; `check` uses a 60% target when the journal row is a 400-pt condor.
Journal template gained rule_decision, hedge_width, credit_400_pts, credit_300_pts, earlier_rule_decision. The engine itself has
no FWD option – backtest numbers for the adopted set come from combining the 300/400-pt no-filter runs.
DATA-SOURCE FINDING 11-Oct-2026 (user cross-check): data/nifty_daily.csv from Breeze (download.py --index, 1-day candles) is NOT NSE's
official close – Breeze's daily close is the last traded index value, NSE's official close is the last-30-minute average.
On the 134 dates behind the 67 filter readings: average gap 5.7 pts, max 40 pts (e.g. 10-Nov-2023 19,443.45 vs 19,425.35; 13-Nov-2023
19,440.15 vs 19,443.55). 10-day move differs by 0.04 pts on average, max 0.24. Decisions that flip with NSE official closes:
±2.5% none (earlier rule and main report unchanged, 45 tr ₹66,052); ±2% three – trade 31 (2.11 → 1.96), 35 (1.99 → 2.01), 38 (1.94 → 2.01);
±1.5% one – trade 14 (1.41 → 1.60). Adopted forward-test rule (TP 50% basis): Breeze 31 tr ₹78,057 / −₹5,523; NSE 30 tr ₹77,931 /
−₹5,523 (only trade 38 drops, +₹126). "±2% for both widths, credit 40–45% at 300-pt" variant: Breeze 37 tr ₹72,869 / −₹9,752; NSE
36 tr ₹82,313 / −₹5,523 – because trade 35 (stop-loss) reads 2.01% and is skipped. So that variant's verdict hangs on 0.02 pts of
one reading; do not treat ±2% vs ±1.5% for the 300-pt leg as settled. The forward-test skill already uses NSE official closes
(live readings follow NSE, not Breeze). 2019–Aug-2020 rows in nifty_daily.csv are already NSE. DONE 11-Oct-2026: data/nifty_daily.csv and india_vix_daily.csv
now hold NSE official values for Aug-2020..9-Oct-2026 incl. the weekend special sessions (fetch_index_nse.py --replace; Breeze
backup only in the session scratchpad). Breeze vs NSE by year: avg gap 2020 9.7 / 2021 11.5 / 2022 12.3 / 2023 8.0 / 2024 4.9 pts
(max 245), 2025–26 identical. download.py --index now only fills days the file lacks (never overwrites). Re-run with NSE closes:
main report unchanged (45 tr ₹66,052 / −₹7,527; 400-pt ±2.5% 44 tr ₹83,114 / −₹9,814); every trade's own P&L unchanged; readings
that crossed a line: 14 (1.41 → 1.60), 31 (2.11 → 1.96), 35 (1.99 → 2.01), 38 (1.94 → 2.01). Rule results on NSE closes (2021–26, n /
net / DD): adopted, TP 60% on 400: 30 ₹81,346 −₹5,523; adopted TP 50%: 30 ₹77,931; no floor: 31 ₹78,790; 300-pt limit 1.25%: 27 ₹70,276;
1.75%: 32 ₹84,909 −₹5,523; ±2% both: 36 ₹82,313 (TP 60%: ₹85,729) −₹5,523; ±2.25% both: 39 ₹77,133 −₹7,424; ±2.5% both: 43 ₹77,804
−₹7,424. NOTE: all filter/threshold studies above this entry (dated up to 10-Oct-2026) used Breeze closes; anything decided at
the ±1.5% or ±2% line by trades 14, 31, 35 or 38 should be re-read with that in mind. Working table: scratch sw_nse.pkl.
FINAL FOUR-WAY COMPARISON on NSE official closes (11-Oct-2026; output/final_variant_comparison.xlsx; 1 lot, net; 400-pt trades with the
60% target; n / net / max DD / worst / PF). 2021–26: no filter (300-pt) 66 / ₹47,298 / −₹11,860 / −₹8,529 / 1.67; ±2.5% (300-pt) 45 /
₹66,052 / −₹7,527 / −₹7,243 / 3.20; "±2% both" (400-pt if credit>=45%, 300-pt if 40–45%) 36 (17+19) / ₹85,729 / −₹5,523 / −₹5,523 / 5.67;
ADOPTED (400-pt ±2% & >=45%, 300-pt ±1.5% & >=40%) 30 (17+13) / ₹81,346 / −₹5,523 / −₹5,523 / 7.49. 2019–20: −₹34,106 / −₹40,887; −₹7,579 /
−₹18,795; both credit rules 4 tr +₹7,040 / −₹1,986. 2019–26: 89 / ₹13,192 / −₹42,721; 60 / ₹58,472 / −₹18,795; 40 / ₹92,768 / −₹5,523 (PF 5.56);
34 / ₹88,386 / −₹5,523 (PF 7.09). The two credit rules differ by 6 trades with a 1.5–2% move: 51 +₹3,900, 58 +₹3,077, 31 +₹2,328,
40 +₹908, 22 −₹3,654, 55 −₹2,178 = +₹4,382. Trade 35 (2.01%) is out of both by 0.01.
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
SIX-WAY SUMMARY (11-Oct-2026, NIFTY 2021–26, net; output/six_variant_comparison.xlsx): adds (6) ±2%, 600-pt TP 60% if 400-pt credit>=45%,
300-pt if 40–45%: 36 tr ₹114,939 / DD −₹5,523 / worst −₹5,523 / win 81% / PF 7.23 / 0.5-pt slip ₹106,879, no losing year – to the five above
(₹47,298; ₹66,052; ₹85,729; ₹110,219 / −₹9,515; ₹100,287).
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
50-DTE ENTRY / 25-DTE EXIT / TP 40% TEST (user request 16-Oct-2026, on the 400-pt C/W variants; 400-pt data downloaded, 300-pt not). User chose
the Monday seven weeks before the expiry week (52 DTE for Thursday expiries, 50 for Tuesday) over exact 50 DTE (would be Wednesdays).
Trade set w7 (make_trades --entry-weeks 7; 68 trades incl. the Apr-2026 expiry; entries 7 days before the reference, 8 for 2208/2504);
strike set d30_w7 to select (~1,300 calls); candles 400-pt ≈ 1,700 calls, 300-pt hedges ≈ 850 more (for the 300-pt tier). New per-run
settings IC_EXIT_DTE / --exit-dte and IC_TP / --tp (defaults 18 / 50; NIFTY reports byte-identical before/after, checked 16-Oct-2026).
Note: holding period 52→25 = 27 days ≈ current 45→18; TP 40% and exit 21+ DTE were each worse on the current timing.
RESULT (18-Oct-2026, 400-pt, 64 common expiries, output/entry50_exit25_tp40_400pt.xlsx; n / net / max DD / losing years) – NOT ADOPTED, do not
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
Open question for the user: NIFTY lot was 75 until the Jun-2021 expiry, but LOT_SIZES uses 50 for Feb–Jun 2021 expiries
(StockMock's quantity); only the 2019–2020 set uses 75.
Future (user idea, not built): 45-DTE short strangle, TP 50% / SL 100% – separate entry script per strategy (e.g.
backtest_strangle.py) reusing ic/engine.py with a 2-leg leg builder; note unlimited risk and much higher margin than the IC.

Action items:
1. Done: 18-DTE StockMock run reconciled; 10-day filter adopted and built in.
2. Decide on the election-results rule (checklist only, or optional engine setting).
3. Fallback-strike rule built in (1-Oct-2026, ic/fallback.py, FALLBACK_SHIFTS −50/+50/−100/+100 then hedge
   350/400; strike_note column). Matches the user's StockMock picks for trades 1, 29, 30, 57; 31 and 33
   differ (StockMock availability / user moved toward 30Δ); 24 has no Breeze data. Downloaded 1-Oct-2026.
   Main report now 45 trades (29, 30, 31 on fallback strikes), net ₹66,052, max DD −₹7,527, win 73%, PF 3.20;
   no-filter 66 trades ₹47,298 / −₹11,860.
4. Paper trade 3–6 months; record real fills and bid-ask of the 300-pt hedges at 11:16; check margin.
5. Done 1-Oct-2026: public repo https://github.com/amitkumarpatel/nifty-iron-condor-backtest (branch main).
   Commit identity (repo-local): amit <1357109+amitkumarpatel@users.noreply.github.com>. User chose to publish
   everything incl. StockMock .xlsx files and this file. Pushing needs the user's PAT (no gh CLI) – run
   `git push` in the user's Terminal; never ask for or handle the token.
6. Review the summary web page (link above).
7. Returns (~₹11.6k/yr with filter) are far below the 1–1.5%/month target – sizing is the user's call.
8. FORWARD-TEST PLAN – SUPERSEDED 10-Oct-2026 by the "Forward-test rule set" section near the top (the list below is now
   the shadow-log rule). Original plan (user's conclusion, 3-Oct-2026), 1 lot, 3–6 months:
   - Skip the month if |NIFTY 10-day move| > 2.5% (close before entry vs close 10 trading days earlier).
   - Monday ~11:15–11:16 entry, ~43 DTE (Tuesday expiries), next-month expiry.
   - Sell ~30Δ CE + PE, buy hedges 300 pts further out (fallback rule if a strike has no price).
   - Exit all legs at the 15:16 check: SL −100% of credit, TP +50%, else time exit at expiry − 18 days.
   - CE-side risk: on any day NIFTY opens >= 1% higher, check and note the condor P&L at 15:16 (gap-up
     exit stays OFF in the engine; shadow-log only). Record bid/ask/fills/margin per leg.
   - Later: same rules with 400-pt hedges (backtest ₹83,114 / DD −₹9,814; with gap-up exit ₹88,148 / −₹6,976).
9. NEW (2-Oct-2026): partial automation in Zerodha + trade journal. Planned scope, in order:
   a. Signal helper (read-only): evening check of the 10-day move, entry-day strike picks (~30Δ sold,
      300-pt hedges, fallback rule), stop/target levels, 18-DTE exit date, daily 15:16 P&L check and
      gap-up flag – alerts only.
   b. Journal: one row per trade/leg (planned vs actual price, bid/ask, slippage, margin, exit reason,
      gap-up shadow result), comparable with export_prices.py output.
   c. Order assistance (later, only if the user asks): prepare the 4-leg order for the user to confirm
      in Kite; never place, modify or cancel orders without explicit per-order confirmation. Hedges
      (buy legs) first, sold legs second; limit orders. Check Kite Connect API terms/costs first.
   Keep it separate from the backtest code (e.g. a live/ package) and keep secrets in .env.
   Started 4-Oct-2026: skill `.claude/skills/nifty-ic-forward-test/` (SKILL.md + scripts/ic_tools.py: rules, filter, plan,
   check, export-ref; journal/ CSVs). `filter` reads NIFTY closes from NSE's daily index files
   (archives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv; no login), falls back to data/nifty_daily.csv with a
   warning; `--closes-file` for Kite-connector data. Kite MCP: read-only tools only.
   Added 4-Oct-2026: `holidays [--write]` (NSE F&O holiday list -> `NSE_HOLIDAYS` block in ic/config.py, forward-test calendar
   only; refresh each January) and `strikes --expiry` (NSE option chain -> ~30Δ sold strikes, 300-pt hedges with the fallback
   rule, bid/ask, credit, target/stop). NSE chain lags a few minutes; user confirms strikes and prices. 2026-11-08 (Sunday
   Muhurat) added to MUHURAT_DAYS. Nov-2026 monthly expiry is Mon 23-Nov (24-Nov holiday) -> entry Mon 12-Oct-2026.
