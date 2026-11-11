# Batman (NIFTY) – rules agreed, backtest to be built

A Batman is a **call ratio spread plus a put ratio spread** on the same expiry: on each side buy 1 option and sell 2
further out. The payoff has two profit peaks near the sold strikes ("bat ears"). With a far bought leg on each side
(a "hedged" Batman, i.e. two broken-wing butterflies) the maximum loss is capped; without it the loss beyond the sold
strikes is unlimited.

## Rules agreed (11-Nov-2026) – first test: unhedged
| Item | Rule |
|---|---|
| Structure | Per side (calls and puts): **buy 1 lot ~20Δ, sell 2 lots ~16Δ** (further out). One sold lot per side is uncovered → unlimited risk beyond the sold strikes |
| Strikes | Deltas from Black-Scholes at 11:16 (option and spot prices), same method as the condor's strike picker; 16Δ and 20Δ must be different strikes |
| Entry | Monday 11:16 at 43 DTE – same dates and expiries as the condor; every month (no filter) |
| Check | Once a day at 15:16 on the whole position, entry day included; stop checked before target |
| Target / stop | **+4% / −4% of the margin blocked at entry** |
| Margin estimate | k × NIFTY spot at entry × lot size; k calibrated from one live Batman margin in Kite's basket (**open**) |
| Time exit | 18 DTE to start (same as the condor); other exit days to be tested |
| Size | 2 + 1 lots per side at each expiry's lot size |
| Periods | 2021–26 (68 cycles) and 2019–20 (24 cycles, out of sample) |

## Next tests (after the first run)
- Hedged Batman: buy 1 far lot per side beyond the 16Δ strike – caps the loss and lowers the margin.
- Exit day (e.g. 7 / 10 / 14 / 18 DTE) and the condor's 10-day move filter as variants.

## Risks to keep in mind
- Unlimited loss beyond the sold strikes; with one check a day a gap can pass the 4% stop by a wide margin.
- Margin of the unhedged version is close to a naked short strangle (very roughly ₹1.2–1.6L at lot 65), so a 4% target / stop
  is about ₹5–6.5k – the estimate of k sets both.

Earlier related test (iron condor work, 21-Oct-2026): a one-sided hedged ratio spread (+1 30Δ, −2 20Δ, +1 20Δ±500) made its
money only when held close to expiry – see README §7 "HEDGED RATIO SPREAD HELD TO EXPIRY".

## Layout (to be filled)
- `config.py` – Batman rules (placeholders until agreed); shared settings come from `shared/config.py`.
- `scripts/` – entry scripts (strike selection, download, backtest).
- `analysis/` – research scripts.
- Data: `data/batman/reference/`; reports: `output/batman/`.
