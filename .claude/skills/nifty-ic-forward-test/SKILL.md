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

Do not quote strategy numbers from memory. Take them from the `rules` output.

## Hard rules

- **Never place, modify or cancel orders.** If a Zerodha Kite MCP is connected, use read-only tools only (for example `get_ltp`, `get_quotes`, `get_ohlc`, `get_historical_data`, `get_positions`). Never call `place_order`, `modify_order`, `cancel_order` or any GTT tool, even if asked mid-session. If the user wants to go live, that is a separate decision they make outside this skill.
- The strategy allows **no adjustments, re-entry, quantity change or extra entry filters**. If the user wants to deviate, say so and log it as a deviation in `notes`. Do not quietly do it.
- Do not give a recommendation to trade. State what the rules say and what the numbers are.
- Never paste or print `.env` contents or the Breeze session token.

## Files

- `journal/forward_trades.csv`: one row per forward-test trade. Create it by copying `assets/forward_trades_template.csv` if missing.
- `journal/forward_daily.csv`: one row per daily check, created by `check --log`.
- Run all commands from the repo root. Put `journal/` in `.gitignore` or commit it, whichever the user prefers (ask once).

## Workflow

### 1. Planning a cycle: `plan`

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py plan --expiry YYYY-MM-DD
```

Shows the entry date and the time-exit date (expiry minus the configured exit DTE, moved back to the previous trading day on holidays, weekends and Muhurat sessions). The calendar only knows holidays listed in `ic/config.py`, so ask the user for any upcoming NSE holiday near the entry or exit date and pass each as `--holiday YYYY-MM-DD`.

The entry date is `ENTRY_DTE` calendar days before expiry (`ic/config.py`). NIFTY monthly expiries have been on Tuesday since Sep-2025, so the entry is 43 DTE: the Monday six weeks before expiry. If that Monday is a holiday, the entry moves to the next trading day (42 DTE). The old 42-45 DTE window belonged to Thursday expiries and is no longer used.

If `plan` prints a NOTE that the expiry is not on the configured weekday, find out why before going on:

- The expiry was moved for a holiday: keep the entry date `plan` prints (the usual Monday).
- NSE changed the expiry day: stop and tell the user. `ENTRY_DTE` and `EXPIRY_WEEKDAY` in `ic/config.py` (and the README rule) must be updated first, and that is the user's decision.

### 2. Evening before entry: `filter`

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py filter --entry-date YYYY-MM-DD --show
```

Prints NIFTY's move over the lookback and **TRADE** or **SKIP**. On SKIP, the month is skipped. Record a row in the journal with a note so the skip is visible later.

Where the closes come from:

- **Default: NSE's website.** The script reads NSE's public daily index file (one small CSV per trading day) for the last 11 sessions. No login and no Breeze token are needed. The file for a day appears in the evening, so run the check after about 18:30, or on the entry morning.
- **Cross-check or alternative: Kite connector.** If a Zerodha Kite MCP is connected, `get_historical_data` (NIFTY 50, daily) is a read-only second source. Save its `date,close` rows to a CSV and pass `--closes-file <path>`.
- **Fallback: `data/nifty_daily.csv`.** Used only when NSE cannot be reached, and the script prints a WARNING. Refresh it with `python download.py --index` (needs a Breeze session token) before trusting the result. `--source nse` or `--source csv` forces one source.

Always pass `--entry-date` so that only closes before the entry day are used, the same as the backtest. Report the two closes and dates the script printed. If it warns that the latest close is stale, do not judge the result.

### 3. Entry at 11:16

The user chooses the strikes. The rules call for ~30-delta sold CE and PE and bought legs `HEDGE_WIDTH` points further out, with the README fallback if a strike has no price. Help only with the following:

- Use read-only Kite quotes if available to show bid, ask and LTP for all four legs. Otherwise ask the user for them.
- Flag a hedge whose bid-ask spread is wide or whose price is at or above its sold leg (the README calls out BAD_PRICE and the slippage risk on the 300-pt hedges).
- Write the trade row: strikes, `paper_px_*` (the paper fills, using the 11:16 prices), `bidask_*`, `filter_move_pct`.

Paper fills are optimistic. Always record real bid and ask at entry so slippage can be estimated later (the README says 1 pt of slippage per leg cuts the 300-pt result to about 11k).

### 4. Daily check at 15:16: `check`

```
python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py check --trade-id N \
  --sce <sold CE> --bce <bought CE> --spe <sold PE> --bpe <bought PE> \
  --open <NIFTY open today> --prev-close <previous close> --log
```

Prices are the 15:16 prices of the four legs. It prints credit, P&L, the target and stop levels and one action:

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
- NSE's index file URL (`NSE_INDEX_URL` in the script) can change or be blocked. If the script falls back to the local CSV more than once, tell the user so the source can be fixed.
- Today's NIFTY open for the gap-up log is not in NSE's file until the evening. Take it from a read-only Kite quote or ask the user.
- `plan` treats weekdays as trading days except configured holidays, because `data/nifty_trading_days.csv` only covers past dates.
- Forward-test sample sizes are tiny. One month proves nothing, so do not draw conclusions about the strategy from a single cycle.
