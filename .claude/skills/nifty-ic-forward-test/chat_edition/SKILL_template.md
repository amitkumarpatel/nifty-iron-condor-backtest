---
name: nifty-ic-chat
description: Monthly forward test (paper trading) of Amit's NIFTY iron condor rulebook, for Claude chat and mobile – no repository or internet needed. Use whenever the user mentions the iron condor, IC, forward test, paper trade, the 10-day filter, the entry at 11:16, the 15:16 check, target/stop/time exit, the put credit spread in skipped months, or asks "should I enter this month", "what is my IC doing", "when is the exit date", "log today's check", even without naming the skill.
---

# NIFTY iron condor forward test – chat edition

Paper trading only. Never place, modify or cancel orders. If a Zerodha Kite connector is attached, use only its read-only tools
(quotes, LTP, OHLC, historical data, instruments, positions, holdings); never an order or GTT tool, even if asked. Do not recommend
trading: say what the rules say and show the numbers. Not a licensed advisor.

Rule values built in on __BUILT__ from the backtest repo. Run `rules` at the start of a session and quote numbers from its output,
not from memory. Script: `scripts/ic_chat.py` (Python standard library only). Run it with `python3 scripts/ic_chat.py <command>`
from the skill folder.

## The rulebook (summary – `rules` prints the exact values)

__RULES__

Backtest 2021–26 (1 lot, after costs; small sample, thresholds fitted – not a forecast): condor rule 37 trades ₹90,667, max drawdown
−₹5,523; with the put spread in skipped months 61 trades ₹1,03,880, drawdown −₹5,523. 2019–20 (never fitted) 20 trades +₹12,963.
Batman (ratio spreads) was tested on 13-Nov-2026 and NOT adopted – the condor makes more for the same or less drawdown.

## Where the data comes from

The chat sandbox usually cannot reach NSE. Get the inputs in this order:

1. **Kite connector, if attached** (the user logs in once a day through the link it gives – that is Zerodha's rule):
   - **Closes:** daily candles of `NSE:NIFTY 50`. These may differ by a few points from NSE's official close (an average of the
     last 30 minutes), which is what the rule uses. If the move lands within 0.1 of a threshold, ask the user to confirm the
     closes on NSE's website.
   - **Option chain:** quotes (bid, ask, last) for the monthly NIFTY options of the expiry, found by searching instruments for
     that expiry. Take strikes from about 1,000 points below to 1,000 points above spot. On the entry day, pull them at or just
     after 11:16.
2. **The user** – typed numbers, a pasted table, or a screenshot of NSE's or Kite's option chain. After reading a screenshot,
   repeat the key strikes and prices back and wait for the user to confirm before deciding. Misreading one digit can flip the
   decision.

Never invent a price. If a strike is missing, say so.

## Workflow

**1. Plan the cycle** – `plan --expiry YYYY-MM-DD` prints the entry day (43 DTE Monday) and the time-exit day.

**2. Evening before entry** – the 10-day filter needs three NSE closes, all from before the entry day:
- **last:** the last close before entry;
- **five:** the close 5 trading days before that;
- **ten:** the close 10 trading days before that.

Run `filter --last C --five C --ten C`, or `filter --closes "YYYY-MM-DD:close,..."` with at least 11 closes. Report the verdict. If
the move is inside ±2%, the width is still decided only at 11:16, by the credit.

**3. Entry at 11:16** – write the chain to a file with the header `strike,ce_bid,ce_ask,ce_ltp,pe_bid,pe_ask,pe_ltp` (leave a cell
blank if there is no quote). Then run:
`strikes --expiry D --spot S --chain chain.csv --time "YYYY-MM-DD HH:MM" --move X --move5 Y`
It picks the ~30-delta sold strikes, prices the 400-point and 300-point condors (or the 20-delta put spread when the condor is
skipped), applies the rules and prints a JOURNAL LINE.
- Show the user the decision, the legs, the credit, the target, the stop and the time-exit date.
- Pass on every WARNING and CLOSE CALL line. A credit that does not rise with the width, or a far strike priced above a nearer
  one, means a stale price: check it in the broker.
- Tell the user to save the JOURNAL LINE (notes app, Google Sheet, or the repo's `journal/forward_trades.csv` later). The chat
  keeps no files between conversations. Ask for the actual paper-fill prices; if they differ, update the `paper_px_*` fields in
  the line.

**4. Daily check at 15:16** – the user pastes the journal line and the four current leg prices (from Kite quotes or typed in;
0 for the call legs of a put spread):
`check --row "<journal line>" --now "sce,bce,spe,bpe" [--open O --prev-close P]`
- Report the P&L (points, % of credit, ₹) and the ACTION: HOLD, STOPLOSS, TARGET or TIME.
- One check a day at 15:16; stop first, then target, then time exit.
- A gap-up of 1% or more is logged only (the exit rule is off).
- Give the DAILY JOURNAL LINE to save.

**5. Closing** – on STOPLOSS, TARGET or TIME all legs close at the 15:16 prices. Ask the user to add the exit date, the reason
and the exit prices to their journal line.

## Rules to keep

- No adjustments, re-entry, extra lots or extra filters. If the user deviates, say so and note it as a deviation in the journal
  line's `notes`.
- One month proves nothing; the backtest is not a forecast.
- Holiday lists are built in only for the years `rules` shows. In December, ask the user to rebuild the skill once NSE publishes
  next year's list.
- If the user is at their Mac, the full skill in the repo (`nifty-ic-forward-test`) fetches NSE data itself and keeps the journal.
