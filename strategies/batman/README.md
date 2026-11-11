# Batman (NIFTY) – rules being finalised

A Batman is a **call ratio spread plus a put ratio spread** on the same expiry: on each side buy 1 option and sell 2
further out. The payoff has two profit peaks near the sold strikes ("bat ears"). With a far bought leg on each side
(a "hedged" Batman, i.e. two broken-wing butterflies) the maximum loss is capped; without it the loss beyond the sold
strikes is unlimited.

## Decided (11-Nov-2026)
- Index: NIFTY, monthly expiry, 1 lot.
- Entry: Monday 11:16 at 43 DTE – the same entry dates and expiries as the iron condor (its cached candles can be reused).
- Daily check at 15:16 (same as the condor).
- Exit: a time exit before expiry (the exact DTE is still to be agreed).

## Still to agree before any backtest
| Item | Options to decide |
|---|---|
| Strikes | delta of the bought leg and of the 2 sold legs, call and put side |
| Wing | hedged (far bought leg, how many points beyond the sold strikes) or unhedged |
| Exit DTE | e.g. 7, 5 or 3 days before expiry |
| Target / stop | % of maximum profit, % of the debit/credit, or a NIFTY level |
| Entry filter | none, the condor's 10-day move, a credit/debit test |
| Data | strike selection (`select_strikes`-style, ~30 calls a month) and candles to the exit DTE (hold to near expiry needs new downloads) |

Earlier related test (iron condor work, 21-Oct-2026): a one-sided hedged ratio spread (+1 30Δ, −2 20Δ, +1 20Δ±500) made its
money only when held close to expiry – see README §7 "HEDGED RATIO SPREAD HELD TO EXPIRY".

## Layout (to be filled)
- `config.py` – Batman rules (placeholders until agreed); shared settings come from `shared/config.py`.
- `scripts/` – entry scripts (strike selection, download, backtest).
- `analysis/` – research scripts.
- Data: `data/batman/reference/`; reports: `output/batman/`.
