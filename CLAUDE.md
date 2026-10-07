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
- Data source: ICICI Breeze (free, exact strike+expiry, 1-min). Probe run confirmed coverage
  2022–2026 fully, 2021 mostly; prices within a few tenths of StockMock; net credit within ~1.5 pts.
- Costs modelled approximately in `config.COSTS` (~₹250 per condor); report gross and net.

## Layout
- Entry scripts in root: `login_url.py`, `probe.py`, `download.py`, `backtest.py`, `select_strikes.py`, `export_prices.py`, `make_trades.py`, `fetch_index_nse.py`
- Code in `ic/`: `config.py`, `breeze_client.py`, `common.py`, `downloader.py`, `engine.py`, `export.py`, `fallback.py`, `probe.py`, `strikes.py`, `cli.py`, `tradeset.py`, `nse_index.py`
- Reference data (committed): `data/reference/ic_reference_trades.csv`, `ic_reference_legs.csv`,
  `stockmock_export.xlsx`; validation workbook in `docs/`
- Generated (git-ignored): `data/cache/` (1-min candles), `data/nifty_trading_days.csv`, `output/`

## Commands
```bash
source .venv/bin/activate
python tests/smoke_test.py      # offline end-to-end test (fake Breeze) – run after code changes
python login_url.py             # daily Breeze login URL
python probe.py [--trades ..]   # data availability check (API)
python download.py              # fetch candles (API, restart-safe, ~3,100 calls)
python download.py --index      # NIFTY + India VIX daily OHLC only (API, a few calls)
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
Summary web page: https://claude.ai/artifact/SHyqgqYkgyeEAg4FkPVwqm (republish on changes).
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
User leans towards the two-tier rule (7-Oct-2026); not yet adopted in config – still fitted, see warning above.
Trade 60's 18-Dec-2025 candles for the 200 and 400-pt hedges were downloaded 7-Oct-2026; 400-pt results unchanged (₹83,114).
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
8. FORWARD-TEST PLAN (user's conclusion, 3-Oct-2026), 1 lot, 3–6 months:
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
