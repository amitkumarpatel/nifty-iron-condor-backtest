"""
Batman strike selection: for every monthly cycle pick, on each side (calls and puts), the strike whose Black-Scholes
delta at 11:16 is nearest BUY_DELTA (bought, 1 lot) and the strike nearest SELL_DELTA further out (sold, 2 lots).
Same method as the condor's picker: NIFTY spot at 11:16, implied volatility from each option's 11:16 price,
r = RISK_FREE_RATE. Only prices from a candle at or before 11:16 (EXACT / FFILL) are used, so every chosen strike
has a usable entry price. The sold strike is always further out than the bought one.

Run:  python strategies/batman/scripts/select_strikes.py --dry-run     (count the Breeze calls; no login)
      python strategies/batman/scripts/select_strikes.py               (needs today's Breeze session)
Output: data/batman/strike_sets/strikes_<STRIKE_SET>.csv and output/batman/strike_selection_<STRIKE_SET>.csv
"""
import argparse
from types import SimpleNamespace

import pandas as pd

from strategies.batman import config as C
from strategies.batman.common import load_cycles, years, strike_file
from shared.calendar import cache_file, contract_key
from shared.options_math import bs, implied_vol
from shared.pricing import price_at, candles

STEP = C.STRIKE_STEP


def centre(spot, ref_strike, ref_px, T, opt, target):
    """Strike whose Black-Scholes delta is nearest `target`, using the implied volatility of a reference strike."""
    iv = implied_vol(ref_px, spot, ref_strike, T, opt) if ref_px and spot else None
    if not iv:
        return None
    grid = range(int(spot * 0.6) // STEP * STEP, int(spot * 1.4), STEP)
    return min(grid, key=lambda k: abs(abs(bs(spot, k, T, iv, opt)[1]) - target))


def delta_of(t, opt, k):
    day = t.entry_date.date()
    spot = price_at(C.SPOT_KEY, day, C.ENTRY_TIME)[0]
    px, q, m = price_at(contract_key(t.expiry.strftime("%Y-%m-%d"), k, opt), day, C.ENTRY_TIME)
    T = years(day, t.expiry)
    iv = implied_vol(px, spot, k, T, opt) if px and spot else None
    d = abs(bs(spot, k, T, iv, opt)[1]) if iv else None
    return dict(trade_id=t.trade_id, entry_date=day, expiry=t.expiry.date(), lot=t.lot, opt_type=opt, strike=k, spot=spot,
                price=px, quality=q, iv=iv and round(iv, 4), delta=d and round(d, 4))


def main():
    ap = argparse.ArgumentParser(description="Pick the Batman strikes (bought ~20 delta, sold ~16 delta) at 11:16")
    ap.add_argument("--trades", type=int, nargs="*", help="only these cycles (trade ids of the condor's reference list)")
    ap.add_argument("--name", default=C.STRIKE_SET, help="strike set name -> strikes_<name>.csv")
    ap.add_argument("--dry-run", action="store_true", help="only count the API calls needed (no login)")
    a = ap.parse_args()
    cyc = load_cycles(a.trades)
    targets = (C.BUY_DELTA, C.SELL_DELTA)
    out_dir = 1                                  # CE: further out = higher strike; PE: lower

    # ---- first window: SEARCH_AROUND strikes each side of the estimate of each target strike ----
    plan, no_est = {}, []
    for t in cyc.itertuples():
        day, exp = t.entry_date.date(), t.expiry.strftime("%Y-%m-%d")
        spot = price_at(C.SPOT_KEY, day, C.ENTRY_TIME)[0]
        T = years(day, t.expiry)
        for opt, ref in (("CE", t.ref_sell_ce), ("PE", t.ref_sell_pe)):
            ref_px = price_at(contract_key(exp, int(ref), opt), day, C.ENTRY_TIME)[0]
            ks = set()
            for tgt in targets:
                c = centre(spot, int(ref), ref_px, T, opt, tgt)
                if c is None:
                    no_est.append((t.trade_id, opt))
                    c = int(ref) // STEP * STEP + (STEP * 4 if opt == "CE" else -STEP * 4)
                ks |= set(range(c - C.SEARCH_AROUND * STEP, c + C.SEARCH_AROUND * STEP + 1, STEP))
            plan[(t.trade_id, opt)] = ks

    def missing(pl):
        out = []
        for (tid, opt), ks in pl.items():
            t = cyc[cyc.trade_id == tid].iloc[0]
            day, exp = t.entry_date.date(), t.expiry.strftime("%Y-%m-%d")
            out += [SimpleNamespace(expiry=exp, opt_type=opt, strike=k, key=contract_key(exp, k, opt), day=day)
                    for k in sorted(ks) if not cache_file(contract_key(exp, k, opt), day).exists()]
        return out

    todo = missing(plan)
    print(f"{len(cyc)} cycles; {sum(len(v) for v in plan.values())} candidate strikes; {len(todo)} API calls needed "
          f"(entry-day candles not cached yet); up to {C.MAX_EXTEND_ROUNDS} small extra rounds if a target is outside "
          f"the window.")
    if no_est:
        print(f"No volatility estimate for {no_est} - searched around the condor strike instead.")
    if a.dry_run:
        return
    api = None

    def fetch(legs):
        nonlocal api
        if not legs:
            return
        from shared.breeze_client import connect
        from shared.breeze_data import Api, fetch_chunk
        api = api or Api(connect())
        for n, leg in enumerate(legs, 1):
            status, msg = fetch_chunk(api, leg, [leg.day])
            if status == "ERROR":
                print(f"  {leg.key} {leg.day}: {msg}")
            if n % 100 == 0:
                print(f"  {n}/{len(legs)}")
        candles.cache_clear()

    try:
        fetch(todo)
        # ---- widen the window while a target delta is not bracketed by priced strikes ----
        for _ in range(C.MAX_EXTEND_ROUNDS):
            extra = {}
            for (tid, opt), ks in plan.items():
                t = cyc[cyc.trade_id == tid].iloc[0]
                rows = [delta_of(t, opt, k) for k in ks]
                ok = [r for r in rows if r["delta"] and r["quality"] in ("EXACT", "FFILL")]
                if not ok:
                    continue
                sgn = 1 if opt == "CE" else -1
                if min(r["delta"] for r in ok) > min(targets):        # all too close to the money -> go further out
                    edge = max(ks) if opt == "CE" else min(ks)
                    extra[(tid, opt)] = {edge + sgn * STEP * n for n in range(1, C.SEARCH_AROUND + 1)}
                elif max(r["delta"] for r in ok) < max(targets):      # all too far out -> come closer
                    edge = min(ks) if opt == "CE" else max(ks)
                    extra[(tid, opt)] = {edge - sgn * STEP * n for n in range(1, C.SEARCH_AROUND + 1)}
            if not extra:
                break
            print(f"extending the search for {len(extra)} legs")
            fetch(missing(extra))
            for key, ks in extra.items():
                plan[key] |= ks
    except RuntimeError as e:
        if str(e) != "DAILY_LIMIT":
            raise
        print("Stopped at the daily call limit - run again tomorrow (progress is saved).")
    if api:
        print(f"API calls this run: {api.calls}")

    # ---- deltas and the pick ----
    cand = pd.DataFrame([delta_of(cyc[cyc.trade_id == tid].iloc[0], opt, k) for (tid, opt), ks in plan.items() for k in sorted(ks)])
    C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cand.to_csv(C.OUTPUT_DIR / f"strike_selection_{a.name}.csv", index=False)
    ok = cand[cand.delta.notna() & cand.quality.isin(["EXACT", "FFILL"])]
    picks, none = [], []
    for (tid, opt), g in ok.groupby(["trade_id", "opt_type"]):
        buy = g.loc[(g.delta - C.BUY_DELTA).abs().idxmin()]
        further = g[g.strike > buy.strike] if opt == "CE" else g[g.strike < buy.strike]
        if not len(further):
            none.append((tid, opt))
            continue
        sell = further.loc[(further.delta - C.SELL_DELTA).abs().idxmin()]
        for role, r, tgt in (("BUY", buy, C.BUY_DELTA), ("SELL", sell, C.SELL_DELTA)):
            picks.append(dict(trade_id=tid, entry_date=r.entry_date, expiry=r.expiry, lot=r.lot, opt_type=opt, role=role,
                              target_delta=tgt, strike=int(r.strike), delta=r.delta, iv=r.iv, price=r.price,
                              quality=r.quality, spot=r.spot))
    out = pd.DataFrame(picks).sort_values(["entry_date", "opt_type", "role"])
    f = strike_file(a.name)
    f.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(f, index=False)
    full = out.groupby("trade_id").size()
    print(f"\nSaved {len(out)} strikes for {int((full == 4).sum())} of {len(cyc)} cycles -> {f}")
    for opt in ("CE", "PE"):
        for role in ("BUY", "SELL"):
            o = out[(out.opt_type == opt) & (out.role == role)]
            if len(o):
                print(f"  {opt} {role}: target {o.target_delta.iloc[0]:.2f}, chosen delta {o.delta.mean():.3f} "
                      f"(range {o.delta.min():.3f}-{o.delta.max():.3f})")
    gap = out.pivot_table(index=["trade_id", "opt_type"], columns="role", values="strike")
    if len(gap):
        print(f"  gap bought -> sold strike: {(gap.SELL - gap.BUY).abs().mean():.0f} pts on average "
              f"({(gap.SELL - gap.BUY).abs().min():.0f}-{(gap.SELL - gap.BUY).abs().max():.0f})")
    missing_cycles = sorted(set(cyc.trade_id) - set(full[full == 4].index))
    if missing_cycles or none:
        print(f"  no complete strike set (no usable 11:16 price): cycles {missing_cycles}")
    print("Next: python strategies/batman/scripts/download.py --dry-run, then without --dry-run")


if __name__ == "__main__":
    main()
