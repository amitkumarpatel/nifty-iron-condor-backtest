"""
Probe: quick check that Breeze has 1-minute data for the legs and that its prices match
StockMock. For a sample of trades it pulls candles around 11:16 (entry day) and 15:16
(exit day) and compares them with StockMock's prices. Also shows which candle label
(T-1 / T / T+1 minute) matches StockMock best, and a last-traded fallback for thin strikes.

Run:  python probe.py                               default sample of 8 trades (~64 calls)
      python probe.py --trades 9 67                 specific trades
      python probe.py --trades 67 --exit-override 67=2026-09-11
      python probe.py --all                         every trade (~536 calls)
Output: output/probe/probe_results.csv and output/probe/raw/*.json
"""
import argparse
import json
import time
from datetime import datetime, timedelta

import pandas as pd

from ic import config as C
from ic.breeze_client import connect
from ic.common import iso

LEGS_CSV = C.LEGS_CSV
DEFAULT_SAMPLE = [1, 9, 20, 35, 48, 56, 62, 67]   # oldest, holidays, SL, year-cross, Tue expiry, latest
WINDOW_MIN = 5          # fetch HH:MM +/- 5 minutes
LABEL_OFFSETS = [-1, 0, 1]   # compare candles labelled 11:15, 11:16, 11:17
PAUSE_SEC = C.PAUSE_SEC
RAW_DIR = C.PROBE_DIR / "raw"




def fetch(breeze, leg, center: datetime):
    # from market open, so we can fall back to the last traded candle for illiquid strikes
    start = center.replace(hour=9, minute=15)
    end = center + timedelta(minutes=WINDOW_MIN)
    expiry = datetime.fromisoformat(leg.expiry).replace(hour=6)
    params = dict(interval="1minute", from_date=iso(start), to_date=iso(end),
                  stock_code="NIFTY", exchange_code="NFO", product_type="options",
                  expiry_date=iso(expiry), right="call" if leg.opt_type == "CE" else "put",
                  strike_price=str(leg.strike))
    try:
        resp = breeze.get_historical_data_v2(**params)
    except Exception as e:  # network / SDK errors
        resp = {"Status": None, "Error": f"EXCEPTION: {e}", "Success": None}
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fname = RAW_DIR / f"t{leg.trade_id}_{leg.opt_type}{leg.strike}_{center:%Y%m%d_%H%M}.json"
    fname.write_text(json.dumps({"params": params, "response": resp}, default=str, indent=1))
    time.sleep(PAUSE_SEC)
    candles = {}
    for c in (resp or {}).get("Success") or []:
        try:
            candles[datetime.strptime(c["datetime"][:16], "%Y-%m-%d %H:%M")] = float(c["close"])
        except (KeyError, ValueError, TypeError):
            pass
    return candles, (resp or {}).get("Error")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", type=int, nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--exit-override", nargs="*", default=[],
                    help="e.g. 67=2026-09-11 to test a different exit date for trade 67")
    a = ap.parse_args()

    legs = pd.read_csv(LEGS_CSV)
    for ov in a.exit_override:
        tid, d = ov.split("=")
        m = legs.trade_id == int(tid)
        legs.loc[m, "exit_dt"] = d + " " + legs.loc[m, "exit_dt"].str[11:]
        print(f"Override: trade {tid} exit date -> {d}")
    ids = sorted(legs.trade_id.unique()) if a.all else (a.trades or DEFAULT_SAMPLE)
    legs = legs[legs.trade_id.isin(ids)]
    print(f"Probing {len(ids)} trades, {len(legs)} legs, ~{len(legs)*2} API calls")

    breeze = connect()
    rows = []
    for leg in legs.itertuples():
        for which, dt_col, ref_col in (("entry", "entry_dt", "entry_px"), ("exit", "exit_dt", "exit_px")):
            center = datetime.strptime(getattr(leg, dt_col), "%Y-%m-%d %H:%M")
            ref = float(getattr(leg, ref_col))
            candles, err = fetch(breeze, leg, center)
            row = dict(trade_id=leg.trade_id, leg=f"{leg.side} {leg.strike}{leg.opt_type}",
                       expiry=leg.expiry, check=which, time=center.strftime("%Y-%m-%d %H:%M"),
                       stockmock_px=ref, n_candles=len(candles), error=err or "")
            for off in LABEL_OFFSETS:
                t = center + timedelta(minutes=off)
                row[f"close_{t:%H%M}"] = candles.get(t)
            prior = [t for t in candles if t <= center]
            if prior:
                last = max(prior)
                row["ffill_px"] = candles[last]
                row["ffill_time"] = last.strftime("%H:%M")
                row["stale_min"] = int((center - last).total_seconds() // 60)
            else:
                row["ffill_px"] = row["ffill_time"] = row["stale_min"] = None
            rows.append(row)
            tag = "OK " if candles else "NO DATA"
            print(f"  {tag} T{leg.trade_id:>2} {row['leg']:<16} {which:<5} {row['time']}  "
                  f"SM={ref:<7} " + "  ".join(f"{k[6:]}={v}" for k, v in row.items() if k.startswith("close_"))
                  + f"  ffill={row['ffill_px']}@{row['ffill_time']}")

    df = pd.DataFrame(rows)
    C.PROBE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(C.PROBE_DIR / "probe_results.csv", index=False)

    # ---- summary ----
    print("\n================ SUMMARY (paste this back) ================")
    has = df.n_candles > 0
    print(f"Checks with data: {has.sum()}/{len(df)} ({has.mean():.0%})")
    by_year = df.assign(year=df.time.str[:4], has=has).groupby("year")["has"].mean()
    print("Coverage by year:", ", ".join(f"{y}: {v:.0%}" for y, v in by_year.items()))

    # which candle label matches StockMock best (per check, pick the label column)
    best = {}
    for off in LABEL_OFFSETS:
        hits = 0
        for r in df.itertuples():
            center = datetime.strptime(r.time, "%Y-%m-%d %H:%M")
            v = getattr(r, f"close_{center + timedelta(minutes=off):%H%M}", None)
            if v is not None and pd.notna(v) and abs(v - r.stockmock_px) <= max(0.5, 0.02 * r.stockmock_px):
                hits += 1
        best[off] = hits
    for off, h in best.items():
        print(f"Candle label {'T' if off == 0 else f'T{off:+d}'} min: {h}/{len(df)} within max(0.5 pt, 2%) of StockMock")

    # match rate at the exact label, and worst mismatches
    df["breeze_px"] = [getattr(r, f"close_{datetime.strptime(r.time, '%Y-%m-%d %H:%M'):%H%M}")
                       for r in df.itertuples()]
    df["diff"] = df.breeze_px - df.stockmock_px
    miss = df[df.breeze_px.isna()]
    if len(miss):
        print(f"\nMissing exact-minute candle: {len(miss)} checks")
        print(miss[["trade_id", "leg", "check", "time", "n_candles", "error"]].head(15).to_string(index=False))
    worst = df.dropna(subset=["diff"])
    worst = worst.loc[worst["diff"].abs().sort_values(ascending=False).index].head(8)
    print("\nLargest differences at exact minute:")
    print(worst[["trade_id", "leg", "check", "time", "stockmock_px", "breeze_px", "diff"]].to_string(index=False))
    ff = df.dropna(subset=["ffill_px"])
    ff_ok = ((ff.ffill_px - ff.stockmock_px).abs() <= ff.stockmock_px.clip(lower=25) * 0.02).sum()
    print(f"\nLast-traded-at-or-before fallback: price found for {len(ff)}/{len(df)} checks, "
          f"{ff_ok} within max(0.5 pt, 2%) of StockMock")
    stale = ff[ff.stale_min > 0]
    if len(stale):
        print(f"Checks needing fallback (no candle at exact minute): {len(stale)}; "
              f"staleness minutes median {stale.stale_min.median():.0f}, max {stale.stale_min.max():.0f}")
        print(stale[["trade_id", "leg", "check", "time", "stockmock_px", "ffill_px", "ffill_time", "stale_min"]]
              .head(15).to_string(index=False))
    nodata_days = df[df.n_candles == 0].groupby(df.time.str[:10]).size()
    if len(nodata_days):
        print("\nDates where legs had NO candles all morning/day (possible holiday or no trading):")
        print(nodata_days.to_string())
    errs = df[df.error != ""].error.value_counts()
    if len(errs):
        print("\nAPI errors:"); print(errs.head(5).to_string())
    print(f"\nSaved {C.PROBE_DIR / 'probe_results.csv'} and {RAW_DIR}/")


if __name__ == "__main__":
    main()
