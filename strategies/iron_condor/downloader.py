"""
Downloader: download 1-minute candles from ICICI Breeze for every leg of every trade,
for every trading day from entry to the latest possible exit. Restart-safe: already
downloaded contract-days are skipped, so if you hit the daily API limit just run it again
tomorrow with a fresh session token.

Run:  python strategies/iron_condor/scripts/download.py              (all trades)
      python strategies/iron_condor/scripts/download.py --trades 1 2 3
      python strategies/iron_condor/scripts/download.py --index      (only NIFTY and India VIX daily OHLC, a few calls)
"""
import argparse
from datetime import date, timedelta

import pandas as pd

from strategies.iron_condor import config as C
from shared.breeze_client import connect
from shared.breeze_data import Api, build_calendar, fetch_index_daily, fetch_chunk   # noqa: F401 (re-exported)
from strategies.iron_condor.common import load_inputs, load_calendar, time_exit_day, cache_file


def fetch_fallback(api, trades, legs, cal, errors):
    """For trades with a leg that has no usable entry price: fetch the entry day of the fallback
    candidates (strategies/iron_condor/fallback.py), then the full price history of the strikes chosen."""
    from types import SimpleNamespace
    from shared.pricing import candles
    from strategies.iron_condor.fallback import choose
    need_entry = []
    for t in trades.itertuples():
        _, note, checked = choose(t, legs[legs.trade_id == t.trade_id])
        if note:
            day = t.entry_date.date()
            need_entry += [(t, k) for k in dict.fromkeys(checked) if not cache_file(k, day).exists()]
    print(f"Fallback strikes: {len(need_entry)} API calls needed for entry-day prices")
    for t, k in need_entry:
        leg = SimpleNamespace(expiry=t.expiry.strftime("%Y-%m-%d"), opt_type=k[-2:], strike=int(k.split("_")[2][:-2]), key=k)
        status, msg = fetch_chunk(api, leg, [t.entry_date.date()])
        if status == "ERROR":
            errors.append((t.trade_id, k, t.entry_date.date().isoformat(), msg))
    candles.cache_clear()
    todo = []
    for t in trades.itertuples():
        chosen, note, _ = choose(t, legs[legs.trade_id == t.trade_id])
        if not note:
            continue
        tx = time_exit_day(t.expiry.date(), cal)
        end = max(tx, t.ref_exit_date.date()) if pd.notna(t.ref_exit_date) else tx
        days = sorted({t.entry_date.date()} | {d for d in cal if t.entry_date.date() <= d <= end})
        for leg in chosen.itertuples():
            need = [d for d in days if not cache_file(leg.key, d).exists()]
            todo += [(t.trade_id, leg, need[i:i + 2]) for i in range(0, len(need), 2)]
    print(f"Fallback strikes: {len(todo)} API calls needed for the chosen strikes")
    for tid, leg, chunk in todo:
        status, msg = fetch_chunk(api, leg, chunk)
        if status == "ERROR":
            errors.append((tid, leg.key, chunk[0].isoformat(), msg))
    return True


def chunks(t, leg, cal):
    """Day pairs of one leg (entry -> time exit / StockMock exit) that are not cached yet - one API call each."""
    tx = time_exit_day(t.expiry.date(), cal)
    end = max(tx, t.ref_exit_date.date()) if pd.notna(t.ref_exit_date) else tx
    days = sorted({t.entry_date.date()} | {d for d in cal if t.entry_date.date() <= d <= end})
    need = [d for d in days if not cache_file(leg.key, d).exists()]
    return [need[i:i + 2] for i in range(0, len(need), 2)]


def main():
    ap = argparse.ArgumentParser(description="Download Breeze 1-minute candles for all trade legs")
    ap.add_argument("--trades", type=int, nargs="*", help="only these trade ids")
    ap.add_argument("--index", action="store_true", help="only daily OHLC of NIFTY, India VIX and the traded index")
    ap.add_argument("--dry-run", action="store_true", help="only count the API calls needed (no login, no calls)")
    a = ap.parse_args()
    trades, legs = load_inputs(a.trades)

    if a.dry_run:
        cal = load_calendar(trades.entry_date.min().date(), trades.expiry.max().date())
        n = sum(len(chunks(t, leg, cal)) for t in trades.itertuples()
                for leg in legs[legs.trade_id == t.trade_id].itertuples())
        print(f"{n} API calls needed for {len(trades)} trades (strike set '{C.STRIKE_SET or 'StockMock'}', hedges "
              f"{C.HEDGE_WIDTH_CE}/{C.HEDGE_WIDTH_PE} pts); fallback strikes may add a few. "
              f"Limit per day {C.DAILY_CALL_LIMIT}.")
        return
    api = Api(connect())
    if a.index:   # ~100 trading days before the first entry, for moving averages
        fetch_index_daily(api, trades.entry_date.min().date() - timedelta(days=150), date.today())
        print(f"API calls this run: {api.calls}")
        return
    errors, complete = [], False
    first = trades.entry_date.min().date()
    last = max(trades.expiry.max().date(), date.today())
    try:
        build_calendar(api, first, min(last, date.today()))
        cal = load_calendar(first, trades.expiry.max().date())

        # work list: (leg, [day1, day2]) chunks not yet cached
        todo = [(t.trade_id, leg, chunk) for t in trades.itertuples()
                for leg in legs[legs.trade_id == t.trade_id].itertuples() for chunk in chunks(t, leg, cal)]
        print(f"{len(todo)} API calls needed (limit per run {C.DAILY_CALL_LIMIT}, already used {api.calls})")

        for n, (tid, leg, chunk) in enumerate(todo, 1):
            status, msg = fetch_chunk(api, leg, chunk)
            if status == "ERROR":
                errors.append((tid, leg.key, chunk[0].isoformat(), msg))
                if "session" in msg.lower() or "unauthor" in msg.lower():
                    print(f"\nSession problem: {msg}\nGenerate a new session token and run again.")
                    break
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} calls  (errors so far: {len(errors)})")
        else:
            complete = fetch_fallback(api, trades, legs, cal, errors) if C.FALLBACK_STRIKES else True
    except RuntimeError as e:
        if str(e) != "DAILY_LIMIT":
            raise
        print(f"\nStopped at the daily call limit ({C.DAILY_CALL_LIMIT}). Progress is saved - "
              "run again tomorrow with a new session token.")

    print(f"\nAPI calls this run: {api.calls}")
    if errors:
        C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ef = C.OUTPUT_DIR / "download_errors.csv"
        pd.DataFrame(errors, columns=["trade_id", "contract", "from_day", "error"]).to_csv(ef, index=False)
        print(f"{len(errors)} chunks failed -> {ef} (they will be retried next run)")
    elif complete:
        print("All requested data downloaded. Next: python strategies/iron_condor/scripts/backtest.py")


if __name__ == "__main__":
    main()
