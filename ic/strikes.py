"""
Delta-based strike selection: for every trade, pick the sold CE and/or PE whose Black-Scholes delta
at entry (ENTRY_TIME, NIFTY spot at that minute) is closest to a target, e.g. a 25-delta call.

Candidates are the StockMock sold strike and strikes around it (STRIKE_STEP apart). Only the entry-day
candles are downloaded here (1 call per NIFTY spot day and per candidate strike, skipped if cached).
Result: data/strike_sets/strikes_<name>.csv, used with IC_STRIKE_SET=<name> by download.py/backtest.py.

Run:  python select_strikes.py --ce-delta 0.25 --name ce25
      python select_strikes.py --trend-shift --with-delta 0.20 --name shiftA          (only trend months)
      python select_strikes.py --trend-shift --with-delta 0.20 --against-delta 0.35 --name shiftB
"""
import argparse
import math
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from ic import config as C
from ic.common import cache_file, contract_key, iso, load_inputs


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, vol, opt):
    """Black-Scholes (price, delta) of a European option; T in years."""
    r, q = C.RISK_FREE_RATE, C.DIV_YIELD
    d1 = (math.log(S / K) + (r - q + vol * vol / 2) * T) / (vol * math.sqrt(T))
    d2 = d1 - vol * math.sqrt(T)
    if opt == "CE":
        return (S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2), math.exp(-q * T) * _ncdf(d1))
    return (K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1), -math.exp(-q * T) * _ncdf(-d1))


def implied_vol(px, S, K, T, opt):
    lo, hi = 0.01, 3.0
    if not bs(S, K, T, lo, opt)[0] < px < bs(S, K, T, hi, opt)[0]:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bs(S, K, T, mid, opt)[0] < px else (lo, mid)
    return (lo + hi) / 2


def fetch_spot_day(api, day):
    r = api.hist(interval="1minute", from_date=iso(datetime(day.year, day.month, day.day, 9, 15)),
                 to_date=iso(datetime(day.year, day.month, day.day, 15, 30)),
                 stock_code="NIFTY", exchange_code="NSE", product_type="cash")
    rows = r.get("Success") or []
    df = pd.DataFrame(rows)
    f = cache_file(C.SPOT_KEY, day)
    f.parent.mkdir(parents=True, exist_ok=True)
    if len(df):
        df["datetime"] = df["datetime"].astype(str).str[:19]
        df = df[[c for c in ["datetime", "open", "high", "low", "close"] if c in df.columns]]
    else:
        df = pd.DataFrame(columns=["datetime", "open", "high", "low", "close"])
    df.to_csv(f, index=False)


def main():
    ap = argparse.ArgumentParser(description="Pick sold strikes by target delta at entry")
    ap.add_argument("--ce-delta", type=float, help="target call delta, e.g. 0.25")
    ap.add_argument("--pe-delta", type=float, help="target put delta as a positive number, e.g. 0.30")
    ap.add_argument("--name", required=True, help="strike set name -> strikes_<name>.csv")
    ap.add_argument("--range", type=int, default=400, help="search this many points further out than the StockMock strike")
    ap.add_argument("--closer", type=int, default=2, help="also search this many strikes closer than the StockMock strike")
    ap.add_argument("--trades", type=int, nargs="*")
    ap.add_argument("--trend-shift", action="store_true",
                    help="only months beyond the trend-filter limit; --with-delta for the leg on the trend side "
                         "(CE after a rise, PE after a fall), --against-delta for the other leg")
    ap.add_argument("--with-delta", type=float, help="trend-shift: delta of the leg on the trend side, e.g. 0.20")
    ap.add_argument("--against-delta", type=float, help="trend-shift: delta of the other leg, e.g. 0.35 (default: unchanged)")
    ap.add_argument("--dry-run", action="store_true", help="only count the API calls needed")
    ap.add_argument("--limit", type=float, help="trend-shift: |10-day move| limit (default SKIP_IF_10D_MOVE_PCT or 2.5)")
    a = ap.parse_args()

    saved, C.STRIKE_SET = C.STRIKE_SET, ""          # candidates are built around StockMock's strikes
    trades, legs = load_inputs(a.trades)
    C.STRIKE_SET = saved
    from ic.engine import price_at                  # after config is final

    # per-trade targets {opt_type: delta}
    if a.trend_shift:
        if not a.with_delta:
            raise SystemExit("--trend-shift needs --with-delta")
        from ic.common import trend_moves
        lim = a.limit or C.SKIP_IF_10D_MOVE_PCT or 2.5
        mv = trend_moves(trades.entry_date)
        trades = trades[[abs(mv[d]) > lim for d in trades.entry_date]]
        per_trade = {}
        for t in trades.itertuples():
            up = mv[t.entry_date] > 0
            with_leg, against_leg = ("CE", "PE") if up else ("PE", "CE")
            per_trade[t.trade_id] = {k: v for k, v in ((with_leg, a.with_delta), (against_leg, a.against_delta)) if v}
        print(f"Trend-shift months (|{C.TREND_LOOKBACK_DAYS}-day move| > {lim}%): {len(trades)} - "
              f"{sum(mv[d] > 0 for d in trades.entry_date)} after a rise, {sum(mv[d] < 0 for d in trades.entry_date)} after a fall")
    else:
        targets = {k: v for k, v in (("CE", a.ce_delta), ("PE", a.pe_delta)) if v}
        if not targets:
            raise SystemExit("Give --ce-delta and/or --pe-delta (or --trend-shift --with-delta)")
        per_trade = {tid: targets for tid in trades.trade_id}
    targets = {o: 1 for tg in per_trade.values() for o in tg}          # option types involved (for the summary)

    # ---- work list: spot days and candidate contracts with no entry-day candles yet ----
    plan, todo_spot, todo_opt = [], set(), []
    for t in trades.itertuples():
        day, exp = t.entry_date.date(), t.expiry.strftime("%Y-%m-%d")
        if not cache_file(C.SPOT_KEY, day).exists():
            todo_spot.add(day)
        for opt, tgt in per_trade[t.trade_id].items():
            ref = int(legs[(legs.trade_id == t.trade_id) & (legs.side == "SELL") & (legs.opt_type == opt)].strike.iloc[0])
            sgn = 1 if opt == "CE" else -1            # further OTM = higher CE / lower PE strike
            for k in range(ref - sgn * a.closer * C.STRIKE_STEP, ref + sgn * (a.range + 1), sgn * C.STRIKE_STEP):
                key = contract_key(exp, k, opt)
                plan.append((t.trade_id, day, t.expiry, opt, tgt, ref, k, key))
                if not cache_file(key, day).exists():
                    todo_opt.append(SimpleNamespace(expiry=exp, opt_type=opt, strike=k, key=key, day=day))
    print(f"{len(todo_spot) + len(todo_opt)} API calls needed ({len(todo_spot)} spot days, {len(todo_opt)} option-days)")
    if a.dry_run:
        return
    if todo_spot or todo_opt:
        from ic.breeze_client import connect
        from ic.downloader import Api, fetch_chunk
        api = Api(connect())
        for n, day in enumerate(sorted(todo_spot), 1):
            fetch_spot_day(api, day)
        for n, leg in enumerate(todo_opt, 1):
            status, msg = fetch_chunk(api, leg, [leg.day])
            if status == "ERROR":
                print(f"  {leg.key} {leg.day}: {msg}")
            if n % 100 == 0:
                print(f"  {n}/{len(todo_opt)}")
        print(f"API calls this run: {api.calls}")

    # ---- deltas at entry ----
    rows = []
    for tid, day, expiry, opt, tgt, ref, k, key in plan:
        spot, sq, _ = price_at(C.SPOT_KEY, day, C.ENTRY_TIME)
        px, q, _ = price_at(key, day, C.ENTRY_TIME)
        T = (datetime.combine(expiry.date(), datetime.strptime("15:30", "%H:%M").time())
             - datetime.combine(day, datetime.strptime(C.ENTRY_TIME, "%H:%M").time())) / timedelta(days=365)
        iv = implied_vol(px, spot, k, T, opt) if px and spot else None
        delta = abs(bs(spot, k, T, iv, opt)[1]) if iv else None
        rows.append(dict(trade_id=tid, entry_date=day, opt_type=opt, target=tgt, ref_strike=ref, strike=k, spot=spot,
                         spot_quality=sq, price=px, quality=q, iv=iv and round(iv, 4), delta=delta and round(delta, 4)))
    cand = pd.DataFrame(rows)
    C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cand.to_csv(C.OUTPUT_DIR / f"strike_selection_{a.name}.csv", index=False)

    ok = cand[cand.delta.notna() & cand.quality.isin(["EXACT", "FFILL"])]
    pick = (ok.assign(err=(ok.delta - ok.target).abs()).sort_values("err")
              .groupby(["trade_id", "opt_type"], as_index=False).first())
    ref_d = cand[cand.strike == cand.ref_strike][["trade_id", "opt_type", "delta"]].rename(columns={"delta": "ref_delta"})
    pick = pick.merge(ref_d, on=["trade_id", "opt_type"], how="left")
    missing = sorted(set(trades.trade_id) - set(pick.trade_id))
    out = pick[["trade_id", "opt_type", "strike", "delta", "iv", "spot", "price", "quality", "ref_strike", "ref_delta"]]
    Path(C.STRIKE_SETS_DIR).mkdir(parents=True, exist_ok=True)
    f = Path(C.STRIKE_SETS_DIR) / f"strikes_{a.name}.csv"
    out.sort_values(["trade_id", "opt_type"]).to_csv(f, index=False)

    print(f"\nSaved {len(out)} strikes -> {f}")
    for opt in targets:
        o = out[out.opt_type == opt]
        if len(o):
            print(f"{opt}: StockMock strike delta {o.ref_delta.mean():.3f} (range {o.ref_delta.min():.2f}-{o.ref_delta.max():.2f}); "
                  f"chosen delta {o.delta.mean():.3f}; chosen strike is {(o.strike - o.ref_strike).abs().mean():.0f} pts "
                  f"further out on average")
    if missing:
        print(f"No strike chosen (no spot/option price at entry): trades {missing} - they keep StockMock's strike")
    print(f"Next: IC_STRIKE_SET={a.name} python download.py, then IC_STRIKE_SET={a.name} python backtest.py --out ...")
