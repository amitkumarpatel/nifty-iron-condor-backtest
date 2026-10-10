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

Adopted on 10-Oct-2026, from the October-2026 cycle. The numbers below are the values at adoption; `rules` prints the live ones from `ic/config.py` (`FWD_*`). If they differ, the `rules` output wins and the user should be told.

### Two readings

| When | Reading | How to get it |
|---|---|---|
| Evening before entry | NIFTY's 10-day move: last close against the close 10 trading days earlier | `filter --entry-date YYYY-MM-DD` |
| 11:16 on the entry day | Net credit of the **400-point** condor: sold ~30-delta call and put, hedges 400 points further out | `strikes --expiry YYYY-MM-DD` |

### Decision table

| 10-day move | Credit of the 400-point condor | Decision | Profit target |
|---|---|---|---|
| within ±1.5% | 180 points or more (45% of width or more) | **400-point condor** | 60% of credit |
| within ±1.5% | 160 to 180 points (40% to 45%) | **300-point condor** | 50% of credit |
| within ±1.5% | below 160 points (below 40%) | **Skip**: minimum-credit floor | none |
| between 1.5% and 2% | 180 points or more | **400-point condor** | 60% of credit |
| between 1.5% and 2% | below 180 points | **Skip** | none |
| beyond ±2% | any | **Skip** | none |

What the evening reading already tells the user:

- within ±1.5%: a trade is expected; the credit at entry decides the width (or a skip, if it is under the floor).
- between 1.5% and 2%: a trade only if the premium is rich at entry.
- beyond ±2%: no trade this month.

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
| 400 points | `FWD_WIDE_WIDTH` |
| ±2% | `FWD_WIDE_MOVE_PCT` |
| 45% of width (180 points) | `FWD_WIDE_MIN_CREDIT_PCT` |
| ±1.5% | `FWD_NARROW_MOVE_PCT` |
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

### Notes to keep in mind

- A single ±2% limit for both widths was considered and not used: it lets in three losing trades and deepens the backtest drawdown.
- The thresholds were chosen on backtest data and the rule trades about five times a year. Do not present its backtest results as what to expect.
- The credit is only known at 11:16. When the evening reading is between 1.5% and 2%, tell the user the decision is still open until entry.

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

- **FORWARD-TEST RULE:** `TRADE` (width decided at entry by the credit), `TRADE ONLY IF RICH` (400-point condor only if its credit reaches the rich line at entry, else skip) or `SKIP`.
- **earlier rule (shadow log):** TRADE or SKIP.

Report both. When the forward-test rule says SKIP, the month is skipped: record a journal row with a note so the skip is visible later. If the earlier rule would have traded, it still needs its shadow row at entry time.

Where the closes come from:

- **Default: NSE's website.** The script reads NSE's public daily index file (one small CSV per trading day) for the last 11 sessions. No login and no Breeze token are needed. The file for a day appears in the evening, so run the check after about 18:30, or on the entry morning.
- **Cross-check or alternative: Kite connector.** If a Zerodha Kite MCP is connected, `get_historical_data` (NIFTY 50, daily) is a read-only second source. Save its `date,close` rows to a CSV and pass `--closes-file <path>`.
- **Fallback: `data/nifty_daily.csv`.** Used only when NSE cannot be reached, and the script prints a WARNING. Refresh it with `python download.py --index` (needs a Breeze session token) before trusting the result. `--source nse` or `--source csv` forces one source.

Always pass `--entry-date` so that only closes before the entry day are used, the same as the backtest. Report the two closes and dates the script printed. If it warns that the latest close is stale, do not judge the result.

### 3. Entry at 11:16

The rules call for ~30-delta sold CE and PE and bought legs `HEDGE_WIDTH` points further out, with the README fallback if a strike has no price. The script works this out from NSE's option chain:

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py strikes --expiry YYYY-MM-DD --save journal/entry_quotes_N.csv
```

It prints the five strikes nearest 0.30 delta on each side (Black-Scholes delta from the bid-ask mid, the same method as the backtest's `select_strikes.py`), then prices **both** the 400-point and the 300-point condor and prints:

- the **forward-test decision**: 400-point condor, 300-point condor or SKIP, with the reason (10-day move and the 400-point credit as points and as a percentage of width);
- what the **earlier rule** would do, for the shadow log;
- for each width: the four legs with bid and ask, the credit at those prices and at bid/ask, the target (higher for the 400-point condor), the stop and the maximum loss.

The 10-day move is worked out from NSE closes before the entry day; `--move X.XX` overrides it. If a hedge has no usable price the README fallback is applied and noted. If the 400-point condor cannot be priced at all, the credit test cannot be made: say so and let the user decide from broker quotes.

Limits to state when reporting it:

- NSE's website chain lags the market by a few minutes, and outside market hours it is the last snapshot (the script warns when it is more than 10 minutes old). Run it at about 11:16 on the entry day. Earlier runs are a preview only.
- A strike flagged WIDE has an unreliable price and delta. Show the neighbouring strikes from the table so the user can prefer a liquid one.
- The script points to the strikes the rules give. The user decides the strikes and confirms prices in the broker terminal.

Then:

- Use read-only Kite quotes if available to confirm bid, ask and LTP for all four legs. Otherwise use the script's output or ask the user.
- Flag a hedge whose bid-ask spread is wide or whose price is at or above its sold leg (the README calls out BAD_PRICE and the slippage risk on the 300-pt hedges).
- Write the trade row: strikes, `paper_px_*` (the paper fills, using the 11:16 prices), `bidask_*`, `filter_move_pct`, `rule_decision` (400 / 300 / SKIP), `hedge_width`, `credit_400_pts`, `credit_300_pts` and `earlier_rule_decision`.
- If the earlier rule would have acted differently (traded when this rule skips, or a 300-point condor when this rule takes 400), add the shadow row for its 300-point condor.

Paper fills are optimistic. Always record real bid and ask at entry so slippage can be estimated later (the README says 1 pt of slippage per leg cuts the 300-pt result to about 11k).

### 4. Daily check at 15:16: `check`

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py check --trade-id N \
  --sce <sold CE> --bce <bought CE> --spe <sold PE> --bpe <bought PE> \
  --open <NIFTY open today> --prev-close <previous close> --log
```

Prices are the 15:16 prices of the four legs. The script reads the hedge width from the journal row and uses the matching profit target (the higher one for a 400-point condor). It prints credit, P&L, the target and stop levels and one action:

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

It prints the rows for `data/reference/ic_reference_trades.csv` and `data/reference/ic_reference_legs.csv`. It does not write to them. Show the output, and append only if the user agrees. After that follow README section 5.8 and 5.10, step 5: `python download.py`, then `python backtest.py`, and compare the forward fills with the backtest's prices for the same trade. `qty_stockmock` is informational only, and the engine uses `config.LOT_SIZES`.

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
