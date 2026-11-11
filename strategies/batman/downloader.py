"""
Batman candle download: 1-minute candles of the four chosen strikes of every cycle, for every trading day from entry
to the time exit (EXIT_DTE). Restart-safe: cached contract-days are skipped, so after the daily API limit just run it
again the next day with a new session token. Shares the cache with the iron condor (data/shared/cache/).

Run:  python strategies/batman/scripts/download.py --dry-run          (count the calls; no login)
      python strategies/batman/scripts/download.py [--exit-dte 7]     (needs today's Breeze session)
"""
import argparse
from types import SimpleNamespace

from strategies.batman import config as C
from strategies.batman.common import load_cycles, load_strikes
from shared.calendar import cache_file, contract_key, load_calendar, time_exit_day


def work(cyc, strikes, exit_dte):
    """(trade_id, leg, [day1, day2]) chunks not cached yet - one API call each."""
    todo = []
    for t in cyc.itertuples():
        s = strikes[strikes.trade_id == t.trade_id]
        if len(s) < 4:
            continue
        e, x = t.entry_date.date(), t.expiry.date()
        cal = load_calendar(e, x)
        tx = time_exit_day(x, cal, exit_dte)
        days = [d for d in cal if e <= d <= tx]
        exp = t.expiry.strftime("%Y-%m-%d")
        for r in s.itertuples():
            leg = SimpleNamespace(expiry=exp, opt_type=r.opt_type, strike=int(r.strike), key=contract_key(exp, r.strike, r.opt_type))
            need = [d for d in days if not cache_file(leg.key, d).exists()]
            todo += [(t.trade_id, leg, need[i:i + 2]) for i in range(0, len(need), 2)]
    return todo


def main():
    ap = argparse.ArgumentParser(description="Download the Batman legs' 1-minute candles (entry -> time exit)")
    ap.add_argument("--trades", type=int, nargs="*")
    ap.add_argument("--exit-dte", type=int, default=C.EXIT_DTE, help=f"download up to this time exit (default {C.EXIT_DTE})")
    ap.add_argument("--dry-run", action="store_true", help="only count the API calls needed (no login)")
    a = ap.parse_args()
    cyc, strikes = load_cycles(a.trades), load_strikes()
    todo = work(cyc, strikes, a.exit_dte)
    print(f"{len(todo)} API calls needed for {strikes.trade_id.nunique()} cycles (strike set {C.STRIKE_SET}, "
          f"time exit {a.exit_dte} DTE). Limit per day {C.DAILY_CALL_LIMIT}.")
    if a.dry_run or not todo:
        return
    from shared.breeze_client import connect
    from shared.breeze_data import Api, fetch_chunk
    api, errors = Api(connect()), []
    try:
        for n, (tid, leg, chunk) in enumerate(todo, 1):
            status, msg = fetch_chunk(api, leg, chunk)
            if status == "ERROR":
                errors.append((tid, leg.key, chunk[0].isoformat(), msg))
                if "session" in msg.lower() or "unauthor" in msg.lower():
                    print(f"\nSession problem: {msg}\nGenerate a new session token and run again.")
                    break
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} calls  (errors so far: {len(errors)})")
    except RuntimeError as e:
        if str(e) != "DAILY_LIMIT":
            raise
        print(f"\nStopped at the daily call limit ({C.DAILY_CALL_LIMIT}). Progress is saved - run again tomorrow.")
    print(f"\nAPI calls this run: {api.calls}")
    if errors:
        C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        import pandas as pd
        ef = C.OUTPUT_DIR / "download_errors.csv"
        pd.DataFrame(errors, columns=["trade_id", "contract", "from_day", "error"]).to_csv(ef, index=False)
        print(f"{len(errors)} chunks failed -> {ef} (they will be retried next run)")
    else:
        print("Done. Next: python strategies/batman/scripts/backtest.py")


if __name__ == "__main__":
    main()
