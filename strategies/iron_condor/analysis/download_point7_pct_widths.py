"""Point 7 download: hedge widths as a % of NIFTY at entry (rounded to 100 pts).

Fetches only the option-days the test needs, for two calibrations (union):
  A) 2021-26 average NIFTY (~20,500): wide 1.95% / normal 1.46% / put spread 0.97%
  B) today's NIFTY (~22,500):         wide 1.78% / normal 1.33% / put spread 0.89%
Spreads per month: condor call and put spreads at the wide and normal widths (30-delta sold strikes as in the
backtest) and the 20-delta put spread at its width. If a spread has no usable 11:16 price, the README fallback is
applied (move the spread -50/+50/-100/+100, then widen the hedge +50/+100): entry-day prices of the candidates
are fetched first, then the full period of the first usable pair.

Run from the repo root after today's Breeze login:
    python strategies/iron_condor/analysis/download_point7_pct_widths.py --dry-run     # count calls only (no login)
    python strategies/iron_condor/analysis/download_point7_pct_widths.py
Restart-safe: cached option-days are skipped.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from strategies.iron_condor import config as C, engine as E                                   # noqa: E402
from strategies.iron_condor.common import contract_key, load_calendar, time_exit_day, cache_file  # noqa: E402

C.EXIT_DTE = 18
REF = pd.concat([pd.read_csv("data/iron_condor/reference/ic_reference_trades.csv"),
                 pd.read_csv("data/iron_condor/reference/ic_trades_2019_2020.csv")]).set_index("trade_id")
CLOSE = pd.read_csv("data/shared/nifty_daily.csv", parse_dates=["date"]).set_index("date").close.sort_index()
D30 = pd.read_csv("data/iron_condor/strike_sets/strikes_d30_2019_2020.csv")
P20 = {}
for n in ("d20_skip", "d20_rest", "d20_2019_2020", "d20_icm", "d20_icm_2019_2020"):
    f = pd.read_csv(f"data/iron_condor/strike_sets/strikes_{n}.csv")
    P20.update(dict(zip(f[f.opt_type == "PE"].trade_id, f[f.opt_type == "PE"].strike)))
CALIB = {"A_avg2021_26": 20530, "B_today": 22500}
BASE = {"wide": 400, "normal": 300, "pcs": 200}


class Leg:
    def __init__(self, expiry, strike, opt):
        self.expiry, self.strike, self.opt_type = expiry, int(strike), opt
        self.key = contract_key(expiry, int(strike), opt)


def months():
    for t in REF.index:
        if t == 24:            # no Breeze data at all
            continue
        e = pd.Timestamp(REF.entry_date[t]).date()
        x = pd.Timestamp(REF.expiry[t]).date()
        spot = CLOSE[CLOSE.index < pd.Timestamp(e)].iloc[-1]
        if t < 1000:
            ce, pe = REF.sell_ce[t], REF.sell_pe[t]
        else:
            s = D30[D30.trade_id == t].set_index("opt_type").strike
            ce, pe = s.get("CE", REF.sell_ce[t]), s.get("PE", REF.sell_pe[t])
        yield t, e, x, spot, int(ce), int(pe), P20.get(t)


def spreads():
    """(trade, entry, expiry, opt, sold, hedge-distance) for every spread the test prices."""
    seen = set()
    for t, e, x, spot, ce, pe, p20 in months():
        for base in CALIB.values():
            w = {k: max(100, int(round(v / base * spot / 100) * 100)) for k, v in BASE.items()}
            items = [("CE", ce, w["wide"]), ("PE", pe, w["wide"]), ("CE", ce, w["normal"]), ("PE", pe, w["normal"])]
            if p20 is not None:
                items.append(("PE", int(p20), w["pcs"]))
            for it in items:
                if (t,) + it not in seen:
                    seen.add((t,) + it)
                    yield (t, e, x) + it


def period_days(e, x):
    cal = load_calendar(e, x)
    tx = time_exit_day(x, cal)
    return [d for d in cal if e <= d <= tx]


def need(leg, days):
    miss = [d for d in days if not cache_file(leg.key, d).exists()]
    return [miss[i:i + 2] for i in range(0, len(miss), 2)]


def usable(leg, day):
    px, q, m = E.price_at(leg.key, day, C.ENTRY_TIME)
    return px if (px is not None and not (q == "AFTER" and abs(m) > C.MAX_AFTER_MIN_AT_ENTRY)) else None


def candidates(opt, k, w):
    out = 1 if opt == "CE" else -1
    tries = [(k, k + out * w)]
    tries += [(k + out * s, k + out * (s + w)) for s in C.FALLBACK_SHIFTS]
    tries += [(k, k + out * (w + extra)) for extra in C.FALLBACK_HEDGE_EXTRA]
    return tries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sp = list(spreads())
    # pass 1: the rule's own strikes, full period
    todo = []
    for t, e, x, opt, k, w in sp:
        days = period_days(e, x)
        for kk in (k, k + (w if opt == "CE" else -w)):
            leg = Leg(str(x), kk, opt)
            todo += [(leg, c) for c in need(leg, days)]
    uniq = {(l.key, tuple(c)): (l, c) for l, c in todo}
    print(f"{len(sp)} spreads; pass 1 (rule strikes, full period): {len(uniq)} API calls")
    if a.dry_run:
        print("Fallback passes (only for spreads without a usable 11:16 price) add a few more; counted after pass 1.")
        return
    from shared.breeze_client import connect
    from strategies.iron_condor.downloader import Api, fetch_chunk
    api = Api(connect())

    def run(items, label):
        items = list({(l.key, tuple(c)): (l, c) for l, c in items}.values())
        print(f"{label}: {len(items)} API calls")
        for n, (leg, c) in enumerate(items, 1):
            status, msg = fetch_chunk(api, leg, c)
            if status == "ERROR" and ("session" in msg.lower() or "unauthor" in msg.lower()):
                sys.exit(f"Session problem: {msg} - log in again and re-run (progress is saved).")
            if n % 50 == 0 or n == len(items):
                print(f"  {n}/{len(items)}")

    try:
        run(uniq.values(), "pass 1")
        # pass 2: entry-day prices of fallback candidates for spreads with no usable price
        bad = []
        for t, e, x, opt, k, w in sp:
            s_, h_ = usable(Leg(str(x), k, opt), e), usable(Leg(str(x), k + (w if opt == "CE" else -w), opt), e)
            if not (s_ and h_ and h_ < s_):
                bad.append((t, e, x, opt, k, w))
        cand = [(Leg(str(x), kk, opt), [e]) for t, e, x, opt, k, w in bad for pair in candidates(opt, k, w)[1:]
                for kk in pair if not cache_file(contract_key(str(x), kk, opt), e).exists()]
        print(f"{len(bad)} spreads need the fallback rule")
        run(cand, "pass 2 (fallback candidates, entry day)")
        # pass 3: full period of the first usable fallback pair
        full = []
        for t, e, x, opt, k, w in bad:
            for ks, kb in candidates(opt, k, w)[1:]:
                s_, h_ = usable(Leg(str(x), ks, opt), e), usable(Leg(str(x), kb, opt), e)
                if s_ and h_ and h_ < s_:
                    days = period_days(e, x)
                    full += [(Leg(str(x), kk, opt), c) for kk in (ks, kb) for c in need(Leg(str(x), kk, opt), days)]
                    break
        run(full, "pass 3 (fallback strikes, full period)")
    except RuntimeError as err:
        if str(err) != "DAILY_LIMIT":
            raise
        print("Stopped at the daily call limit - run again tomorrow (progress is saved).")
    print(f"API calls this run: {api.calls}. Tell Claude 'point 7 data downloaded'.")


if __name__ == "__main__":
    main()
