# Batman (NIFTY) – rules agreed, backtest to be built

A Batman is a **call ratio spread plus a put ratio spread** on the same expiry: on each side buy 1 option and sell 2
further out. The payoff has two profit peaks near the sold strikes ("bat ears"). With a far bought leg on each side
(a "hedged" Batman, i.e. two broken-wing butterflies) the maximum loss is capped; without it the loss beyond the sold
strikes is unlimited.

## Rules agreed (11-Nov-2026) – first test: unhedged
| Item | Rule |
|---|---|
| Structure | Per side (calls and puts): **buy 1 lot ~20Δ, sell 2 lots ~16Δ** (further out). One sold lot per side is uncovered → unlimited risk beyond the sold strikes |
| Strikes | Deltas from Black-Scholes at 11:16 (option and spot prices), same method as the condor's strike picker, **nearest delta** (option A, user 11-Nov-2026); the sold strike is always further out than the bought one |
| Entry | Monday 11:16 at 43 DTE – same dates and expiries as the condor; every month (no filter) |
| Check | Once a day at 15:16 on the whole position, entry day included; stop checked before target |
| Target / stop | **+4% / −4% of the margin blocked at entry** |
| Capital | **Static ₹2.5L for the tests** (user, 11-Nov-2026) → target = stop = **₹10,000** in every month. (A margin scaled by NIFTY × lot, k = 0.159 from the sample, was set aside.) |
| Time exit | 18 DTE to start (same as the condor); other exit days to be tested |
| Size | 2 + 1 lots per side at each expiry's lot size |
| Period | 2021–26 (68 cycles) only for now; 2019–20 later |

## StockMock sample trade (11-Nov-2026, `data/batman/reference/Batman strategy 43DTE entry ..._StockMock.xlsx`)
Entry Mon 13-Jul-2026 11:16, expiry 25-Aug-2026, time exit Fri 7-Aug-2026 15:16 (18 DTE), lot 65: buy 25100 CE @103 and 23350 PE @135.5,
sell 2 × 25200 CE @82 and 2 × 23150 PE @105.2 → net credit 135.9 pts (₹8,834). StockMock P&L +₹6,039 (time exit).
Checked on Breeze: all four contracts cached, prices within 0.2 pts; replay with the shared simulator +₹6,052 gross / ₹5,694 net, same
time exit; never near ±₹10,000 (range −₹777 … +₹6,201). Our Black-Scholes deltas at 11:16 (r 6.5%): 25100 CE 0.207, 25200 CE 0.174,
25300 CE 0.149, 23350 PE 0.198, 23150 PE 0.159 → same strikes as StockMock except the 16Δ call, where 25200 (0.174) and 25300 (0.149)
are about equally near 0.16 and our nearest-delta rule picks 25300. Delta models differ slightly; a full StockMock run would let us
reconcile every month as for the condor.

## Next tests (after the first run)
- Hedged Batman: buy 1 far lot per side beyond the 16Δ strike – caps the loss and lowers the margin.
- Exit day (e.g. 7 / 10 / 14 / 18 DTE) and the condor's 10-day move filter as variants.

## Risks to keep in mind
- Unlimited loss beyond the sold strikes; with one check a day a gap can pass the 4% stop by a wide margin.
- Margin of the unhedged version is close to a naked short strangle (very roughly ₹1.2–1.6L at lot 65), so a 4% target / stop
  is about ₹5–6.5k – the estimate of k sets both.

Earlier related test (iron condor work, 21-Oct-2026): a one-sided hedged ratio spread (+1 30Δ, −2 20Δ, +1 20Δ±500) made its
money only when held close to expiry – see README §7 "HEDGED RATIO SPREAD HELD TO EXPIRY".

## How to run (from the repository root)
```bash
python shared/scripts/login_url.py                          # today's Breeze session (only for the first two steps)
python strategies/batman/scripts/select_strikes.py          # 20Δ / 16Δ strikes at 11:16 for the 68 cycles (~150 calls)
python strategies/batman/scripts/download.py --dry-run      # count the candle calls (no login)
python strategies/batman/scripts/download.py --exit-dte 7   # candles entry -> 7 DTE (covers the 18-DTE exit too; ~700 calls)
python strategies/batman/scripts/backtest.py                # offline -> output/batman/BATMAN_backtest_report.xlsx
python strategies/batman/scripts/backtest.py --exit-dte 10  # another time exit -> BATMAN_backtest_report_x10.xlsx
```

## Layout
- `config.py` – Batman rules (placeholders until agreed); shared settings come from `shared/config.py`.
- `common.py` (cycles, strikes), `strikes.py` (delta picker), `downloader.py`, `engine.py` (backtest + report).
- `scripts/` – entry scripts: `select_strikes.py`, `download.py`, `backtest.py`.
- `analysis/` – research scripts.
- Data: `data/batman/reference/`; reports: `output/batman/`.
