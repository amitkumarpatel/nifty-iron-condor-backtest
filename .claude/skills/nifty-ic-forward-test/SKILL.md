---
name: nifty-ic-forward-test
description: Run the monthly forward test (paper trading) of the NIFTY iron condor from the nifty-iron-condor-backtest repo. Use whenever the user mentions the iron condor, IC, forward test, paper trade, monthly entry, the 10-day trend filter, the 15:16 check, target/stop/time exit, gap-up logging, or asks "should I enter this month", "what is my IC position doing", "when is the exit date", or "log today's check", even if they don't name the skill. Also use to add a finished forward trade back into the backtest reference files for reconciliation.
---

# NIFTY monthly iron condor: forward test

This skill runs the routine in README section 5.10 ("Monthly routine") of the repo. It is a **paper-trading** workflow. The repo only reads historical data and never places orders, and this skill keeps it that way.

## Source of truth

The rules change often (hedge width, exit DTE and the filter were all revised within one week). So:

1. Run `python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py rules` at the start of every session. It prints the live values from `ic/config.py`.
2. For anything not covered by those values, read **README section 1 (Strategy rules)** and **section 7** in the repo.
3. If this file and `config.py`/README disagree, `config.py`/README win. Tell the user about the mismatch.

Do not quote strategy numbers from memory. Take them from the `rules` output. The decision table below is a reading aid; it does not replace that check.

## The rule set being forward-tested (README section 1b)

Adopted on 10-Oct-2026, finalised on 11-Oct-2026 (one ±2% limit for all widths) and set to a **400-point condor on rich-credit months** on 18-Oct-2026, from the October-2026 cycle. A 600-point condor makes more profit in the backtest, but the user chose 400 points because of the lower risk: its largest possible loss stays within 2–3% of the account. The width is to be reviewed after 6–12 months of forward testing (around April–October 2027). On 27-Oct-2026 the user added a **20-delta put credit spread with a 200-point hedge** for the months the condor rule skips (section "Put credit spread in the skipped months" below); a 300-point hedge makes more profit but is kept as a shadow line for the same reason as 600 points. The numbers below are the values at adoption; `rules` prints the live ones from `ic/config.py` (`FWD_*`). If they differ, the `rules` output wins and the user should be told.

### Combined rulebook at a glance (condor + put spread, 27-Oct-2026; figures corrected 29-Oct-2026)

Every month is one of four outcomes, decided by three readings: the 10-day move and the 5-day move (`filter`, evening before entry) and the 400-point condor credit (`strikes`, 11:16).

| Step | Condition | Trade | Target |
|---|---|---|---|
| 1 | 10-day move within ±2% and 400-pt credit ≥ 180 pts (≥ 45%) | Iron condor, ~30Δ sold, **400-pt** hedges | 60% of credit |
| 2 | 10-day move within ±2% and credit 160–180 pts (40–45%) | Iron condor, **300-pt** hedges | 50% of credit |
| 3 | Otherwise, unless step 4 applies | Put credit spread: sell ~20Δ put, buy the put **200 pts** lower | 50% of its credit |
| 4 | 10-day rise > +2.5% and 5-day move ≤ +1% | Skip the month | – |

For every trade: entry Monday 11:16 at 43 DTE; one check at 15:16 (stop, then target, then time exit); stop at 100% of the trade's own credit; time exit at expiry − 18 days; 1 lot, one position at a time, no adjustment.

| | Version A – traded (lower risk) | Version B – shadow / review (more profit) |
|---|---|---|
| Condor on rich-credit months | 400-pt | 600-pt |
| Put spread | 20Δ / 200-pt | 20Δ / 300-pt (priced and logged every put-spread month) |
| Largest possible loss per lot (65) | condor ≈ ₹13,600 · put spread ≈ ₹11,000 | ≈ ₹22,500 · ≈ ₹16,800 |

Backtest 2021–26, net, no slippage (`output/combined_ic_plus_put20_spread.xlsx`; includes the 29-Oct corrections – see "Data corrections" below):

| Year | Condor | Put spread 200 | **Total (traded)** | Put spread 300 | Total (300 shadow) |
|---|---|---|---|---|---|
| 2021 | ₹13,620 | ₹4,089 | **₹17,709** | ₹5,550 | ₹19,171 |
| 2022 | ₹676 | ₹4,530 | **₹5,206** | ₹6,492 | ₹7,168 |
| 2023 | ₹11,201 | ₹1,018 | **₹12,219** | ₹1,456 | ₹12,657 |
| 2024 | ₹9,135 | ₹500 | **₹9,635** | ₹1,028 | ₹10,163 |
| 2025 | ₹39,122 | ₹2,209 | **₹41,331** | ₹2,954 | ₹42,076 |
| 2026 (to Aug) | ₹16,914 | ₹867 | **₹17,781** | ₹1,362 | ₹18,276 |
| **Total** | **37 tr ₹90,667** | **24 tr ₹13,212** | **61 tr ₹1,03,880** | 24 tr ₹18,842 | 61 tr ₹1,09,510 |

- 2021–26 has 68 monthly cycles: 61 traded (37 condors, 24 put spreads; the same 61 for both versions – May-2024's 300-pt put spread runs on fallback strikes), 5 skipped by step 4 (entries Sep-21, Apr-22, Dec-24, Feb-25, Feb-26) and 2 without usable Breeze data (Dec-22 entry, which would have been a 300-pt condor, StockMock ≈ −₹1,925; Mar-26 entry, a put spread, indicative ≈ +₹2.2k on a week-late entry).
- Combined: 50 W / 11 L (82%), max drawdown −₹5,523 (Aug-26 condor), profit factor 5.54, about ₹1,530 a month = 0.3–0.5% a month on ₹3–5L. With 0.5 pt slippage per leg about ₹93k, with 1 pt about ₹82k.
- Version B with the 600-pt condor is not backtested as a combined set (estimate ≈ ₹1.41L: 600-pt condor rule ₹1,22,477 + 300-pt put spreads ₹18,842). Review both widths together after 6–12 months (about Apr–Oct 2027), with real fills and margin.
- Shadow logs: the 300-pt put spread; the earlier rule (300-pt condor whenever |10-day move| ≤ 2.5%); the condor's 15:16 P&L on every 1% gap-up day.
- Next decision: Monday 16-Nov-2026 for the 29-Dec-2026 expiry (`filter` from the evening of Friday 13-Nov).

### Two readings

| When | Reading | How to get it |
|---|---|---|
| Evening before entry | NIFTY's 10-day move: last close against the close 10 trading days earlier | `filter --entry-date YYYY-MM-DD` |
| 11:16 on the entry day | Net credit of the **400-point** condor: sold ~30-delta call and put, hedges 400 points further out. This condor is the credit test and, when the credit is rich, the trade | `strikes --expiry YYYY-MM-DD` |

### Decision table

| 10-day move | Credit of the 400-point condor | Decision | Profit target |
|---|---|---|---|
| within ±2% | 180 points or more (45% of width or more) | **400-point condor** | 60% of credit |
| within ±2% | 160 to 180 points (40% to 45%) | **300-point condor** | 50% of credit |
| within ±2% | below 160 points (below 40%) | no condor (minimum-credit floor) → **put credit spread** rule below | 50% of its credit |
| beyond ±2% | any | no condor → **put credit spread** rule below | 50% of its credit |

What the evening reading already tells the user:

- within ±2%: a trade is expected; the credit at entry decides the width (or a skip, if it is under the floor).
- beyond ±2%: no condor this month; the put credit spread rule decides (`filter` prints its verdict too).

### Put credit spread in the skipped months (adopted 27-Oct-2026)

| Reading (evening before entry) | Decision |
|---|---|
| Condor skipped, 10-day move above +2.5% **and** the last 5 days added +1% or less (the rally has stalled) | **Skip the month**: nothing traded |
| Condor skipped, any other case (rise with a strong last 5 days, move 2–2.5% either way, any fall, credit under the floor) | **Put credit spread**: sell the ~20-delta put, buy the put **200 points** lower |

| Rule | Value |
|---|---|
| Entry, daily check, time exit, size | same as the condor: Monday 11:16, 15:16 check, expiry minus 18 days, 1 lot |
| Profit target | 50% of the spread's own credit |
| Stop-loss | minus 100% of the spread's own credit |
| Fallback strikes | same rule as the condor (move the spread, then widen the hedge) |
| Shadow line | price and log the same sold put with a **300-point** hedge every time |
| Config | `FWD_PCS_DELTA`, `FWD_PCS_WIDTHS` = [200], `FWD_PCS_ALT_WIDTHS` = [300], `FWD_PCS_RISE_PCT`, `FWD_PCS_MIN_5D_PCT`, `FWD_PCS_TP_FRACTION` |

Backtest 2021–26 (1 lot, net, the 30 months the condor rule skips; `output/put20_credit_spread_all_skipped_filters.xlsx`, `output/combined_ic_plus_put20_spread.xlsx`):

| | 200-point (chosen) | 300-point (shadow; review in 6–12 months) |
|---|---|---|
| Put spread trades / net | 24 / ₹13,212 | 24 / ₹18,842 |
| Won–lost / max drawdown / worst | 21–3 / −₹1,891 / −₹1,891 | 21–3 / −₹2,573 / −₹2,573 |
| Average credit | 30 points (≈ ₹2,000 a lot) | 42 points |
| Largest possible loss per lot (65) | ≈ ₹11,000 (2.2% of ₹5L, 3.7% of ₹3L) | ≈ ₹16,800 (3.4% of ₹5L, 5.6% of ₹3L) |
| Profit ÷ average largest loss | 1.20× | 1.12× |
| Condor + put spread | 61 trades ₹1,03,880, DD −₹5,523 | 61 trades ₹1,09,510, DD −₹5,523 |

Why 200 and not 300: 300 points makes about ₹5.6k more over six years, but only because each trade carries about 50% more risk; per rupee at risk it is slightly worse, and its largest loss breaks the 2–3% rule. Same reasoning as 400 vs 600 for the condor; review both widths together.

Small print: the 5-day filter was chosen on these 30 months; only 3 put spreads lost, so the stop is barely tested; the profit per trade is small (≈ ₹550), so fills matter. 2019–20 out of sample (lot 75, 5-day filter, corrected 29-Oct): 200-point 16 trades +₹5,965, 13–3, drawdown −₹5,281; 300-point 16 trades +₹7,278, drawdown −₹7,028. Losers Jul-19, Sep-19 and Sep-20 (falls of 3–6%). Mar-2020 (no price) and Apr-2020 (only a few odd trades on the put strikes) could not be tested. With the 4 condors of those years: 20 trades +₹12,963, drawdown −₹5,281 (200-point). Leg-by-leg detail of every put spread: `output/pcs_trade_details.xlsx`.

**Size (user decision, 29-Oct-2026): 1 lot.** The put spread needs about half the margin of the 400-point condor, but 2 lots would carry a largest possible loss of about ₹22,000 (7.4% / 5.5% / 4.4% of ₹3L / ₹4L / ₹5L) – outside the 2–3% limit, like the 600-point condor. Backtest at 2 lots: 2021–26 rulebook ₹1,17,094 with the same −₹5,523 drawdown, but 2019–20 put-spread drawdown −₹10,562 and worst trade −₹8,974. Revisit at the 6–12-month review with real fills; 2 lots fit 3% only from an account of about ₹7.4L. If the user asks again, give these numbers; sizing is the user's call.

### Same for both widths

| Rule | Value |
|---|---|
| Entry | Monday, 11:16, next-month expiry (43 DTE for Tuesday expiries) |
| Sold strikes | ~30 delta call and put; fallback rule if a strike has no price |
| Stop-loss | P&L at or below minus 100% of the credit |
| Daily check | once, at 15:16; order is stop-loss, then target, then time exit |
| Time exit | last trading day on or before expiry minus 18 days |
| Size | 1 lot; no adjustment, no re-entry |
| Gap-up exit | off; log every day NIFTY opens 1% or more above the previous close |

### Config names behind the table

| Value | Setting in `ic/config.py` |
|---|---|
| 400 points: the credit-test condor | `FWD_SIGNAL_WIDTH` |
| 400 points: the condor traded on rich-credit months (a list; add 600 to paper trade both) | `FWD_WIDE_WIDTHS` |
| ±2% for the wide condor | `FWD_WIDE_MOVE_PCT` |
| 45% of width (180 points) | `FWD_WIDE_MIN_CREDIT_PCT` |
| ±2% for the 300-point condor (was ±1.5% until 11-Oct-2026) | `FWD_NARROW_MOVE_PCT` |
| 40% of width (160 points) | `FWD_MIN_CREDIT_PCT` |
| 60% target | `FWD_WIDE_TP_FRACTION` |
| 300 points, 50% target, 100% stop, 18 days | `HEDGE_WIDTH`, `TP_FRACTION`, `SL_FRACTION`, `EXIT_DTE` |

### Shadow log: the earlier rule

The earlier rule is kept for comparison: a 300-point condor whenever the 10-day move is within ±2.5% (`SKIP_IF_10D_MOVE_PCT`), 50% target, same stop and exits. Every month, also record what it would have done.

| Forward-test decision | Earlier rule | What to log |
|---|---|---|
| 300-point condor | 300-point condor | One row; both rules agree |
| 400-point condor | 300-point condor | The real 400-point row, plus a shadow row for the 300-point condor |
| Skip | 300-point condor | A skip row, plus a shadow row for the 300-point condor |
| Skip | Skip | A skip row only |

A shadow row holds the 300-point condor's strikes and 11:16 prices and has `shadow` in `notes`. Run the daily `check` for it too, so its exit and P&L can be compared later.

### Backtest of this rule set

1 lot, net of costs, NSE official closes for the 10-day move, 60% target on the 400-point trades. The first table is the rule being forward-tested; the second compares hedge widths on the same months. Files: `output/variants_400_500_600_corrected.xlsx` (29-Oct, with the corrections), older `output/six_variant_comparison.xlsx`, `output/risk_reward_400_vs_600.xlsx`.

| Period | Trades (400 / 300) | Net P&L | Max drawdown | Worst trade | Win rate | Profit factor |
|---|---|---|---|---|---|---|
| 2021–26 | 37 (18 / 19) | ₹90,667 | −₹5,523 | −₹5,523 | 78% | 5.94 |
| 2019–20 | 4 (2 / 2) | ₹7,040 | −₹1,986 | −₹1,986 | 75% | 4.54 |
| 2019–26 | 41 (20 / 21) | ₹97,707 | −₹5,523 | −₹5,523 | 78% | 5.8 |

Earlier rule (shadow log) on the same data: 2021–26 45 trades, ₹69,855, drawdown −₹7,527; 2019–26 60 trades, ≈ ₹62,300, drawdown −₹18,795.

| Condor on the 18 rich-credit months (2021–26, same 37 trades in total) | Net P&L | Max drawdown | Profit factor | Largest possible loss on one rich-month trade (lot 65) |
|---|---|---|---|---|
| **400-point (chosen)** | ₹90,667 | −₹5,523 | 5.94 | about ₹13,600 |
| 500-point (not chosen) | ₹1,06,462 | −₹5,523 | 6.81 | about ₹17,900 |
| 600-point (more profit, more risk; review in 6–12 months) | ₹1,22,477 | −₹5,523 | 7.63 | about ₹22,500 |

The drawdown is identical because it comes from a 300-point trade. No rich-credit month in the backtest lost more than about ₹1,600 at 400 points (about ₹2,000 at 600), so the last column has never been tested. 2019–20 was only run at 400 points.

### Why 400 points and not 600: risk to reward

600 points gives the better profit in the backtest. 400 points is chosen because its risk is lower. The two trade the same months; only the 17 rich-credit trades differ.

| On the 17 rich-credit months | 400-point (chosen) | 600-point |
|---|---|---|
| Net P&L | ₹59,061 | ₹88,271 |
| Winners / losers | 14 / 3 | 15 / 2 |
| Average win / average loss | ₹4,407 / −₹879 | ₹6,068 / −₹1,372 |
| Average credit | 191.5 points | 254.1 points |
| Largest possible loss per condor | 208.5 points, about ₹13,600 | 345.9 points, about ₹22,500 |
| Loss at the 100% stop (= the credit) | about ₹12,400 | about ₹16,500 |
| Credit ÷ largest possible loss | 0.92 | 0.74 |
| Six-year profit ÷ largest possible loss | 5.2× | 4.7× |
| Largest loss as % of ₹3L / ₹4L / ₹5L | 4.5% / 3.4% / 2.7% | 7.5% / 5.6% / 4.5% |
| Account needed to stay within 3% / 2% | about ₹4.5L / ₹6.8L | about ₹7.5L / ₹11.2L |

- The 600-point condor collects 33% more credit but can lose 66% more. Per rupee at risk it is slightly worse, so the extra profit is a bigger trade, not a better one.
- The user's rule is that one trade's largest possible loss stays within 2–3% of the account. 600 points breaks it anywhere in ₹3–5L; 400 points meets it from about ₹4.5L.
- The 300-point middle tier can lose about ₹10,400 a lot (2.1% of ₹5L).

### Small print behind the numbers

Quote these whenever the user asks how reliable the backtest is. README section 1b has the same list.

**Months with no result**

| Month | Why it is missing | Effect |
|---|---|---|
| December 2022 (trade 24) | Breeze has no option data | It would have been a 300-point trade (move −0.09%, StockMock credit 177.7 points = 44.4%). StockMock shows a loss of ₹1,925 before costs. Counting it: 2021–26 about ₹83.5k, 2022 a small losing year (about −₹1.5k), drawdown about −₹5.8k |
| May 2023 (trade 29) | No Breeze price for the 400-point call hedge at 11:16 | None: move +2.23%, skipped anyway |
| April-2026 expiry (entry 16-Mar-2026) | Not in the trade list | None: move −9.2%, skipped anyway |

**Readings on the ±2% line**

| Trade | 10-day move | What happened |
|---|---|---|
| 35 (November 2023, stop-loss) | +2.01% | Skipped by 0.01. At 2.00% it is a 300-point trade losing ₹7,243: total about ₹78.5k, drawdown about −₹7.4k |
| 38 (February 2024) | +2.01% | Skipped; harmless (+₹126 at 400 points) |
| 43 (July 2024) | +2.05% | Skipped; a +₹1,937 winner missed |
| 4 (April 2021) | +1.96% | Traded, 400-point, +₹2,469 |
| 31 (July 2023) | +1.96% | Traded, 300-point, +₹2,328 |

The data source decides these. With Breeze's last-traded close, trade 35 read +1.99% and trade 31 +2.11%, and the same rule showed ₹76,284 with a −₹9,752 drawdown. Use NSE's official close only.

**Credits on the 160-point floor and the 180-point line**

| Trade | Credit (% of 400) | What happened |
|---|---|---|
| 30 (June 2023) | 160.2 points (40.05%) | In by 0.2 of a point; second-largest loss, −₹3,731 |
| 31 (July 2023) | 162 points (40.5%) | In; +₹2,328 |
| 45 (September 2024) | 158.6 points (39.6%) | Out; a +₹859 winner. The call-hedge price looks like a bad print |
| 53 (May 2025) | 45.7% | Closest 400-point trade; +₹3,645 (+₹2,400 at 300 points) |
| 22 and 55 | 44.4% and 44.5% | Just under 45%, so 300-point; both lost, and less than at 400 points |

**What the rule does not fix**

- The worst trade, August 2026 (trade 67, −₹5,523), passes every test: move −0.07%, credit 43.6%. It is the drawdown.
- 2019–20 barely tests the rule: only 4 of 23 months pass the credit floor.
- The four numbers (2%, 45%, 40%, 60% target) were chosen on this data, and the rule trades about six times a year. Treat the backtest as an upper bound.
- No slippage is included: with 0.5 point per leg 2021–26 is ₹77,669; with 1 point ₹69,609.
- Maximum loss per lot (lot 65): about ₹13,600 for the 400-point condor and ₹10,400 for the 300-point one. The user's limit is 2–3% of the account, so a rich-credit trade needs an account of about ₹4.5L or more. Say so if the account or the lot size changes.
- If the user asks about going back to 600 points, give both sides: more profit in the backtest, but a largest possible loss of about ₹22,500 a lot, outside the 2–3% limit for ₹3–5L. The agreed plan is to review the width after 6–12 months of forward testing, with real fills and margin.
- Widening the 300-point limit from ±1.5% to ±2% added six trades worth +₹4,382 (four winners; losers 22 and 55), with the same drawdown.

### Robustness checks (28-Oct-2026)

Run on the whole rulebook (condor + 20-delta / 200-point put spread), including 2019–20, which the rules were never fitted on. None of them changed a rule. The walk-forward, delta, target and reshuffle rows were measured before the 29-Oct corrections; their conclusions do not depend on them. Files: `output/walk_forward_rulebook_thresholds.xlsx`, `output/put_spread_15_20_25_delta_2019_2026.xlsx`, `output/put_spread_target_exitdte_5day_2019_2026.xlsx`, `output/rulebook_2019_2026_fallback_slippage_thin_credit.xlsx`.

| Check | Result | Verdict |
|---|---|---|
| Whole rulebook 2019–26 (corrected 29-Oct) | 81 trades, ₹1,16,843, max drawdown −₹5,523, no losing year; 2019–20 alone 20 trades +₹12,963 | Holds out of sample |
| Drawdown to plan for | Reshuffling the 80 trades into 20,000 random orders: median worst drawdown −₹6.8k, 1 in 10 −₹11.1k, 1 in 20 −₹12.9k, 1 in 100 −₹16.8k; about 1 path in 4 has a losing year | Plan for about −₹12–13k a lot, not −₹5.5k |
| Walk-forward (900 threshold versions: 10-day limit 1.5–2.5%, rich line 43–47%, floor 36–42%, rise 2–3%, 5-day limit 0.5–1.5%) | All 900 profitable in 2021–23, 2024–26 and 2019–20. Fit 2021–23 → 2024–26: best-fitted ₹60.6k vs current ₹68.2k; fit 2024–26 → 2021–23: ₹28.5k vs current ₹29.7k | Re-optimising does not help; keep the thresholds |
| One threshold at a time | Each step moves 2021–26 by about ±₹3–5k, except a 10-day limit of 2.25–2.5%, which lets in the Nov-2023 stop-loss (drawdown −₹5.5k → −₹9.1k) | ±2% is the line not to widen |
| Sold-put delta | 2019–26: 15Δ ₹6.3k, 20Δ ₹21.8k, 25Δ ₹20.4k; 25Δ/300 best in 2021–26 (₹29.3k) but −₹1.8k with a −₹18.6k drawdown in 2019–20 | 20Δ is the only delta solid in both periods |
| Put-spread target and exit day | Target 40% ≈ 50% (₹21.7k vs ₹21.8k); 60% or more doubles the 2021–26 drawdown; 21 or 25 DTE earn less than 18 | Keep 50% and 18 DTE |
| Slippage per leg (corrected 29-Oct) | 0.5 pt: 2021–26 ₹93.0k; 1 pt: ₹82.1k (drawdown −₹6.0k), still no losing year. Break-even: condor ≈ 5 pts/leg, put spread ≈ 2.2 pts/leg. The live half bid-ask of the 20Δ/200 spread was ≈ 1.3 pts/leg (27-Oct) | Put spread needs limit orders near mid |
| Put spread instead of the condor in calm months | ₹4.0k on the 36 condor months of 2021–26 (drawdown −₹9.2k) vs ₹85.7k for the condors | The condor is right in calm months |
| Fallback strikes for the put spread | Adds May-19 and May-24 (300-pt); everything else unchanged. Mar-2020 (no prices) and Apr-2020 (a few odd trades on the put strikes) untestable | Apply the same fallback rule live |

How to use this live:

- **Stop-test levels to suggest** (the user decides): a drawdown beyond about ₹13,000 a lot, or average slippage above 1 point per leg. Average slippage above about 2 points per leg on the put spread means it no longer earns.
- **Log the put spread's fill against its mid price** at entry and exit. That is the number that decides whether it is worth trading.
- If the user wants to change a threshold, point to the walk-forward: re-fitted thresholds did worse on new data than the current ones. Widening the 10-day limit beyond ±2% is the one change with a known cost.
- **Robust is not the same as safe.** No rich-credit condor and few put spreads lost much in eight years, the March-2020 crash could not be tested for the put spread, and the out-of-sample evidence is 21 trades. The forward test is the real test.
- **User decision (28-Oct-2026):** no credit filter on the put spread. 9 of the 10 thin-credit months were 2019–20, where the fixed 400-point width made the ratio low. Do not propose it again.

### Data corrections (29-Oct-2026) and what they mean live

A leg-by-leg check of the backtest found four problems; all figures above include the fixes.

| Fix | What was wrong | Live lesson |
|---|---|---|
| Lot size, Feb–Jun 2021 expiries | The backtest used 50; NSE kept 75 until the Jun-2021 expiry (circular FAOP47854). `ic/config.py` fixed | The lot that counts is the contract's own lot (NSE changes apply by expiry). Take it from the broker's contract details |
| Sep-2024 entry | The 400-pt call hedge (and the 500/600-pt ones) showed old quotes with zero volume, priced above a nearer strike → credit 158.6 (put spread). Realistic 180.45 = 45.1% → 400-pt condor (+₹942) | A stale far-strike price can flip the decision at the 160 / 180 lines. Use live bid/ask; compare with the neighbouring strikes |
| Mar-2024 expiry, 300-pt put spread | The 20650 PE was an old quote, so the 300-pt spread "collected" less than the 200-pt one | Same check: a wider spread must collect more |
| Entry-day 15:16 check | The put-spread simulator skipped the entry day's 15:16 check (the condor engine had it). No 2021–26 trade changed; Apr-2020's put prices turned out to be unusable | Run `check` at 15:16 on the entry day too – a target or stop can hit the same afternoon |

Files: `output/pcs_trade_details.xlsx` (every put spread, legs, volumes, daily path), `output/combined_ic_plus_put20_spread.xlsx` (Changes sheet), `output/variants_400_500_600_corrected.xlsx`.

### What to do with this live

- When the 10-day reading is within about 0.1 of ±2%, say so and show the two closes used.
- When the 400-point credit is within a few points of 160 or 180, say so and let the user confirm the leg prices before deciding.
- If a hedge is priced oddly against its neighbouring strike, flag it as a possible bad print; it can move the credit across the floor (see "Data corrections" – the backtest had two such months).
- Check the credit ladder before deciding: the 300, 400 (and 500/600 if logged) condor credits, and the 200/300 put-spread credits, must rise with the width. A wider spread collecting less, or a far strike priced above a nearer one, means a stale price – use bid/ask or the neighbouring strikes.
- The credit is only known at 11:16, so an evening reading inside ±2% is not yet a decision on the width.
- Do not present the backtest results as what to expect.

## Hard rules

- **Never place, modify or cancel orders.** If a Zerodha Kite MCP is connected, use read-only tools only (for example `get_ltp`, `get_quotes`, `get_ohlc`, `get_historical_data`, `get_positions`). Never call `place_order`, `modify_order`, `cancel_order` or any GTT tool, even if asked mid-session. If the user wants to go live, that is a separate decision they make outside this skill.
- The strategy allows **no adjustments, re-entry, quantity change or extra entry filters**. If the user wants to deviate, say so and log it as a deviation in `notes`. Do not quietly do it.
- Do not give a recommendation to trade. State what the rules say and what the numbers are.
- Never paste or print `.env` contents or the Breeze session token.

## Files

- `journal/forward_trades.csv`: one row per forward-test trade. Create it by copying `assets/forward_trades_template.csv` if missing.
- `journal/forward_daily.csv`: one row per daily check, created by `check --log`.
- Run all commands from the repo root. `journal/` is in `.gitignore` (the repo is public), so the journal stays on this machine and is never committed.

## Workflow

### 1. Planning a cycle: `plan`

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py plan --expiry YYYY-MM-DD
```

Shows the entry date and the time-exit date (expiry minus the configured exit DTE, moved back to the previous trading day on holidays, weekends and Muhurat sessions). The calendar uses the NSE holiday list in `ic/config.py` (`NSE_HOLIDAYS`). If `plan` warns that a year has no holiday list, refresh it first (below), or pass a known holiday as `--holiday YYYY-MM-DD`.

Holiday list:

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py holidays            # show NSE's list and what would change
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py holidays --write    # update NSE_HOLIDAYS in ic/config.py
```

It reads the F&O trading holidays from NSE's website. Run it without `--write` first and show the user the difference. `--write` edits `ic/config.py`, so do it only when the user agrees, then run `python tests/smoke_test.py` and commit. Refresh it each January (NSE publishes the next year's list in December) and after any special holiday announcement. A date NSE marks `*` is a Muhurat session: tell the user it must also be in `MUHURAT_DAYS`.

Monthly expiries move to the previous trading day when the Tuesday is a holiday, so take the expiry date from NSE's listed expiries (the `strikes` command rejects a date that is not listed and prints the listed ones).

The entry date is `ENTRY_DTE` calendar days before expiry (`ic/config.py`). NIFTY monthly expiries have been on Tuesday since Sep-2025, so the entry is 43 DTE: the Monday six weeks before expiry. If that Monday is a holiday, the entry moves to the next trading day (42 DTE). The old 42-45 DTE window belonged to Thursday expiries and is no longer used.

If `plan` prints a NOTE that the expiry is not on the configured weekday, find out why before going on:

- The expiry was moved for a holiday: keep the entry date `plan` prints (the usual Monday).
- NSE changed the expiry day: stop and tell the user. `ENTRY_DTE` and `EXPIRY_WEEKDAY` in `ic/config.py` (and the README rule) must be updated first, and that is the user's decision.

### 2. Evening before entry: `filter`

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py filter --entry-date YYYY-MM-DD --show
```

Prints NIFTY's 10-day move and two verdicts:

- **FORWARD-TEST RULE:** `TRADE` (width decided at entry by the credit), `TRADE ONLY IF RICH` (the wide condor only if the 400-point credit reaches the rich line at entry, else skip; not used while both move limits are ±2%) or `SKIP`.
- **earlier rule (shadow log):** TRADE or SKIP.

It also prints the 5-day move and, on the line "if the condor is skipped", the put credit spread verdict (PUT CREDIT SPREAD or SKIP the month).

Report all three. When the forward-test rule says SKIP for the condor, the put spread verdict decides; when that also says SKIP, the month is skipped: record a journal row with a note so the skip is visible later. If the earlier rule would have traded, it still needs its shadow row at entry time.

Where the closes come from:

- **Default: NSE's website.** The script reads NSE's public daily index file (one small CSV per trading day, `ind_close_all_DDMMYYYY.csv`) for the last 11 sessions and takes the "Closing Index Value" of the "Nifty 50" row. That is NSE's official close (the last-30-minute average), the same figure the backtest file now holds; it is not the last traded value a broker's daily candle may show. No login and no Breeze token are needed. The file for a day appears in the evening, so run the check after about 18:30, or on the entry morning.
- **Cross-check or alternative: Kite connector.** If a Zerodha Kite MCP is connected, `get_historical_data` (NIFTY 50, daily) is a read-only second source. Save its `date,close` rows to a CSV and pass `--closes-file <path>`. A broker's daily close can differ from NSE's official close by several points; if the two disagree near a limit, the NSE figure decides.
- **Fallback: `data/nifty_daily.csv`.** Used only when NSE cannot be reached, and the script prints a WARNING. The file holds NSE official closes up to the last `python fetch_index_nse.py` run; check its last date before trusting the result. `--source nse` or `--source csv` forces one source.

Always pass `--entry-date` so that only closes before the entry day are used, the same as the backtest. Report the two closes and dates the script printed. If it warns that the latest close is stale, do not judge the result.

### 3. Entry at 11:16

The rules call for ~30-delta sold CE and PE and bought legs `HEDGE_WIDTH` points further out, with the README fallback if a strike has no price. The script works this out from NSE's option chain:

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py strikes --expiry YYYY-MM-DD --save journal/entry_quotes_N.csv
```

It prints the five strikes nearest 0.30 delta on each side (Black-Scholes delta from the bid-ask mid, the same method as the backtest's `select_strikes.py`), then prices the 400-point condor (the credit test, and the trade when the credit is rich) and the 300-point condor, and prints:

- the **forward-test decision**: 400-point condor, 300-point condor or SKIP, with the reason (10-day move and the 400-point credit as points and as a percentage of width);
- what the **earlier rule** would do, for the shadow log;
- for each width: the four legs with bid and ask, the credit at those prices and at bid/ask, the target (60% for the 400-point condor), the stop and the maximum loss. The 400-point block is both the credit test and the trade.

When the condor decision is SKIP it also prints the **put credit spread** block: the 5-day move, the put spread decision, and the 20-delta sold put with the 200-point hedge (CHOSEN) and the 300-point hedge (shadow log), each with bid/ask, credit, target, stop and maximum loss.

The 10-day and 5-day moves are worked out from NSE closes before the entry day; `--move X.XX --move5 Y.YY` override them. If a hedge has no usable price the README fallback is applied and noted. If the 400-point condor cannot be priced at all, the credit test cannot be made: say so and let the user decide from broker quotes.

Limits to state when reporting it:

- NSE's website chain lags the market by a few minutes, and outside market hours it is the last snapshot (the script warns when it is more than 10 minutes old). Run it at about 11:16 on the entry day. Earlier runs are a preview only.
- A strike flagged WIDE has an unreliable price and delta. Show the neighbouring strikes from the table so the user can prefer a liquid one.
- The script points to the strikes the rules give. The user decides the strikes and confirms prices in the broker terminal.

Then:

- Use read-only Kite quotes if available to confirm bid, ask and LTP for all four legs. Otherwise use the script's output or ask the user.
- Flag a hedge whose bid-ask spread is wide or whose price is at or above its sold leg (the README calls out BAD_PRICE and the slippage risk on the 300-pt hedges).
- Write the trade row: strikes, `paper_px_*` (the paper fills, using the 11:16 prices), `bidask_*`, `filter_move_pct`, `rule_decision` (400 / 300 / SKIP), `hedge_width`, `credit_400_pts`, `credit_300_pts` and `earlier_rule_decision` (`credit_500_pts` and `credit_600_pts` stay empty unless those widths are added to `FWD_WIDE_WIDTHS`).
- A put credit spread row: leave `sell_ce` / `buy_ce` and their prices empty, fill `sell_pe` / `buy_pe`, `structure` = PCS, `hedge_width` = 200, `move_5d_pct`, `pcs_credit_200_pts` and `pcs_credit_300_pts`. Add a shadow row for the 300-point put spread (`notes` = shadow). For a condor row, `structure` = IC.
- If the earlier rule would have acted differently (traded when this rule skips, or a 300-point condor when this rule takes the 400-point condor), add the shadow row for its 300-point condor.

Paper fills are optimistic. Always record real bid and ask at entry so slippage can be estimated later (the README says 1 pt of slippage per leg cuts the 300-pt result to about 11k).

### 4. Daily check at 15:16: `check`

The first check is on the entry day itself (15:16), as in the backtest engine.

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py check --trade-id N \
  --sce <sold CE> --bce <bought CE> --spe <sold PE> --bpe <bought PE> \
  --open <NIFTY open today> --prev-close <previous close> --log
```

Prices are the 15:16 prices of the four legs. For a put credit spread leave out `--sce` / `--bce`: the script sees the empty call legs in the journal row and uses the spread's own 50% target and 100% stop. The script reads the hedge width from the journal row and uses the matching profit target (60% for a condor 400 points wide or more). It prints credit, P&L, the target and stop levels and one action:

| Action | Meaning |
| --- | --- |
| STOPLOSS | exit all four legs |
| TARGET | exit all four legs |
| TIME | last trading day on/before expiry minus exit DTE: exit all four legs |
| GAP_UP | only when `GAP_UP_EXIT_PCT` is set in config, and never on the entry day |
| HOLD | do nothing |

The order is stop-loss, then target, then time exit. Checks are once a day at 15:16 with no intraday monitoring. A loss can therefore exceed 100% of credit. Report it as it is.

Pass `--open` every day while a condor is open (`--prev-close` is optional: without it the script takes the previous close from NSE), even with the gap-up exit off. The README asks to log every gap-up at or above the threshold and what a 15:16 exit would have done. Gap-downs must **not** trigger an exit.

### 5. Closing a trade

When an exit action fires and the user has exited, fill `exit_date`, `exit_reason` and the four `exit_px_*` columns in `forward_trades.csv`. Then run:

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py export-ref --trade-id N
```

(For a put credit spread it stops with a message: the backtest reference files hold condors only, so the put spread stays in the journal.) For a condor it prints the rows for `data/reference/ic_reference_trades.csv` and `data/reference/ic_reference_legs.csv`. It does not write to them. Show the output, and append only if the user agrees. After that follow README section 5.8 and 5.10, step 5: `python download.py`, then `python backtest.py`, and compare the forward fills with the backtest's prices for the same trade. `qty_stockmock` is informational only, and the engine uses `config.LOT_SIZES`.

## Reporting style

Keep answers short and numeric. For a check, give: action, P&L in points and as a percent of credit, distance to target and stop, days to the time exit. For a review across trades, show the daily and trade journals as a table, and separate paper P&L from backtest P&L for the same dates.

## Known gaps

- The 10-day filter follows the README: last close before the entry day versus the close 10 trading days earlier, either direction. If the README definition changes, update `cmd_filter` in the script.
- The forward-test rule set lives only in the skill script and `ic/config.py`. `backtest.py` still runs the earlier rule, so after a trade is exported for reconciliation the backtest's 300-point result is the shadow comparison, not a check of a 400-point trade unless it is run with `--hedge 400`.
- The rule's thresholds were chosen on backtest data and it trades about five times a year. Do not present its backtest results as what to expect.
- NSE's index file URL (`NSE_INDEX_URL` in the script) can change or be blocked. If the script falls back to the local CSV more than once, tell the user so the source can be fixed.
- Today's NIFTY open for the gap-up log is not in NSE's file until the evening. Take it from a read-only Kite quote or ask the user.
- `plan` treats weekdays as trading days except the holidays in config (`NSE_HOLIDAYS`, `EXTRA_HOLIDAYS`, `MUHURAT_DAYS`), because `data/nifty_trading_days.csv` only covers past dates. A holiday announced after the last `holidays --write` is missed until it is refreshed.
- NSE's holiday and option-chain addresses are unofficial website endpoints and can change or be blocked. If `holidays` or `strikes` fails, say so and fall back to NSE's holiday page or broker quotes; do not guess.
- Forward-test sample sizes are tiny. One month proves nothing, so do not draw conclusions about the strategy from a single cycle.
