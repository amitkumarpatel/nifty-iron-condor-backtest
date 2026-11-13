"""
Batman backtest (offline, reads the shared candle cache). Rules (strategies/batman/config.py): per side buy BUY_LOTS at
~20 delta and sell SELL_LOTS at ~16 delta, entry Monday 11:16 at 43 DTE, one check a day at 15:16 on the whole
position (entry day included; stop before target), target / stop = 4% of the capital used (config.capital_used), else time exit at
EXIT_DTE. 1 unit (2 + 1 lots per side) at each expiry's lot size. Uses the shared multi-leg simulator.

Run:  python strategies/batman/scripts/backtest.py [--trades ..] [--exit-dte N] [--out file]
Output: output/batman/BATMAN_<variant>_backtest_report[_x<DTE>].xlsx (Read me, Summary, By year, Trades, Daily, Not run, StockMock check)
"""
import argparse
from pathlib import Path

import pandas as pd

from strategies.batman import config as C
from strategies.batman.common import load_cycles, load_strikes, legs_of
from shared import spread_sim
from shared.calendar import contract_key
from shared.pricing import price_at

SAMPLE = {"file": "Batman strategy 43DTE entry sell 2lots 16delta and buy 1 lot 20 delta_StockMock.xlsx", "trade_id": 66,
          "legs": {"25100CE": 103.0, "25200CE": 82.0, "23350PE": 135.5, "23150PE": 105.2}, "pnl": 6039,
          "exit": "2026-08-07", "reason": "TIME"}


def max_dd(s):
    eq = s.cumsum()
    return (eq - eq.cummax().clip(lower=0)).min()


def run_cycle(t, strikes, exit_dte):
    legs = legs_of(strikes, t.trade_id)
    base = dict(trade_id=t.trade_id, entry_date=t.entry_date.date(), expiry=t.expiry.date(), lot=t.lot)
    if not legs:
        return dict(base, status="no strikes (no usable 11:16 prices)"), []
    exp = t.expiry.strftime("%Y-%m-%d")
    spot = price_at(C.SPOT_KEY, t.entry_date.date(), C.ENTRY_TIME)[0]
    cap = C.capital_used(spot, t.lot)
    tp_rs, sl_rs = cap * C.TP_PCT_OF_CAPITAL / 100, cap * C.SL_PCT_OF_CAPITAL / 100
    r = spread_sim.run(t.entry_date, exp, legs, t.lot, tp_pts=tp_rs / t.lot, sl_pts=sl_rs / t.lot,
                       exit_dte=exit_dte, detail=True)
    if r is None:
        return dict(base, status="not priceable (a leg has no entry price or no daily prices)"), []
    row = dict(base, status="run", variant=C.VARIANT)
    roles = {}
    for (p, o, k), role in zip(legs, [r for _ in ("CE", "PE") for r in (["BUY", "SELL", "WING"] if C.WING_OFFSET else ["BUY", "SELL"])]):
        key = contract_key(exp, k, o)
        tag = f"{role.lower()}_{o.lower()}"
        sd = strikes[(strikes.trade_id == t.trade_id) & (strikes.opt_type == o) & (strikes.role == role)]
        row[f"{tag}_strike"] = k
        row[f"{tag}_delta"] = sd.delta.iloc[0] if len(sd) else None
        row[f"{tag}_lots"] = abs(p)
        row[f"{tag}_entry"], row[f"{tag}_entry_q"] = r["legs_entry"][key]
        row[f"{tag}_exit"], row[f"{tag}_exit_q"] = r["legs_exit"][key]
        if "note" in sd and len(sd) and isinstance(sd.note.iloc[0], str):
            roles[o] = sd.note.iloc[0]
    row["strike_note"] = "; ".join(f"{o}: {n}" for o, n in roles.items())
    row["fills_per_side"] = sum(abs(p) for p, _, _ in legs)
    credit = -r["entry_val"]
    path = pd.DataFrame(r["path"])
    row.update(net_credit_pts=round(credit, 2), net_credit_rs=round(credit * t.lot), spot=spot, capital_used_rs=round(cap), target_rs=round(tp_rs), stop_rs=-round(sl_rs),
               exit_date=r["exit_day"], exit_time=C.CHECK_TIME, exit_reason=r["reason"], pnl_pts=round(r["pnl_pts"], 2),
               gross_rs=round(r["gross"], 2), costs_rs=round(r["cost"], 2), net_rs=round(r["net"], 2),
               days_held=(r["exit_day"] - t.entry_date.date()).days,
               best_rs=path.pnl_rs.max() if len(path) else None, worst_rs=path.pnl_rs.min() if len(path) else None,
               non_exact_entry=sum(q != "EXACT" for _, q in r["legs_entry"].values()))
    daily = [dict(trade_id=t.trade_id, **d) for d in r["path"]]
    return row, daily


def summary(tr):
    s = tr.sort_values("exit_date").net_rs
    w, l = s[s > 0], s[s <= 0]
    g = tr.gross_rs
    rows = [("Cycles in 2021-26", None), ("Trades run", len(s)), ("Net P&L (Rs)", round(s.sum())), ("Gross P&L (Rs)", round(g.sum())),
            ("Costs (Rs)", round(tr.costs_rs.sum())), ("Winners / losers", f"{len(w)} / {len(l)}"),
            ("Win rate", f"{len(w) / len(s):.0%}" if len(s) else None),
            ("Targets / stops / time exits", f"{(tr.exit_reason == 'TARGET').sum()} / {(tr.exit_reason == 'STOPLOSS').sum()} / "
                                             f"{(tr.exit_reason == 'TIME').sum()}"),
            ("Max drawdown (Rs, exit order)", round(max_dd(s))), ("Worst trade (Rs)", round(s.min())), ("Best trade (Rs)", round(s.max())),
            ("Average win / loss (Rs)", f"{round(w.mean()) if len(w) else 0} / {round(l.mean()) if len(l) else 0}"),
            ("Profit factor", round(w.sum() / -l.sum(), 2) if len(l) and l.sum() else None),
            ("Average net credit (pts)", round(tr.net_credit_pts.mean(), 1)),
            ("Worst point inside a trade (Rs)", round(tr.worst_rs.min())),
            ("Trades whose final loss passed the stop", int((tr.net_rs < tr.stop_rs).sum())),
            ("Capital used (Rs), average / range", f"{tr.capital_used_rs.mean():,.0f} / {tr.capital_used_rs.min():,.0f}-{tr.capital_used_rs.max():,.0f}"),
            ("Target = stop (Rs), average / range", f"{tr.target_rs.mean():,.0f} / {tr.target_rs.min():,.0f}-{tr.target_rs.max():,.0f}"),
            ("Net with 0.5 pt slippage per lot per fill (Rs)", round((tr.net_rs - 0.5 * 2 * tr.fills_per_side * tr.lot).sum()))]
    return pd.DataFrame(rows, columns=["item", "value"])


HEDGED_SAMPLE = {"trade_id": 66, "legs": {"buy_ce": (24700, 216.9), "sell_ce": (24800, 181.5), "wing_ce": (25300, 67.3),
                                          "buy_pe": (23700, 214.9), "sell_pe": (23600, 187.6), "wing_pe": (23100, 99.0)},
                 "credit_rs": 9106.5, "max_profit": 15544, "max_loss": -16893}


def stockmock_check(tr, strikes):
    """Entry legs of trade 66 (13-Jul-2026) next to the user's StockMock sample (unhedged: file with the full trade;
    hedged: the screenshot of 13-Nov-2026, entry only)."""
    t = tr[tr.trade_id == 66]
    if not len(t):
        return pd.DataFrame()
    t = t.iloc[0]
    if C.WING_OFFSET:
        rows = [dict(leg=tag, engine_strike=t.get(f"{tag}_strike"), engine_delta=t.get(f"{tag}_delta"),
                     engine_entry=t.get(f"{tag}_entry"), stockmock_strike=k, stockmock_entry=px)
                for tag, (k, px) in HEDGED_SAMPLE["legs"].items()]
        rows += [dict(leg="net credit (Rs)", engine_entry=t.net_credit_rs, stockmock_entry=HEDGED_SAMPLE["credit_rs"]),
                 dict(leg="StockMock max profit / max loss (Rs)", stockmock_entry=f"{HEDGED_SAMPLE['max_profit']} / {HEDGED_SAMPLE['max_loss']}")]
        return pd.DataFrame(rows)
    if not (Path(C.REF_DIR) / SAMPLE["file"]).exists():
        return pd.DataFrame()
    rows = []
    for tag in ("buy_ce", "sell_ce", "buy_pe", "sell_pe"):
        o = tag[-2:].upper()
        sm = next((s for s in SAMPLE["legs"] if s.endswith(o) and (("buy" in tag) == (s in ("25100CE", "23350PE")))), None)
        rows.append(dict(leg=tag, engine_strike=t[f"{tag}_strike"], engine_delta=t[f"{tag}_delta"],
                         engine_entry=t[f"{tag}_entry"], stockmock_strike=sm, stockmock_entry=SAMPLE["legs"].get(sm)))
    rows += [dict(leg="P&L (Rs)", engine_entry=t.gross_rs, stockmock_entry=SAMPLE["pnl"]),
             dict(leg="exit", engine_strike=str(t.exit_date), stockmock_strike=SAMPLE["exit"]),
             dict(leg="exit reason", engine_strike=t.exit_reason, stockmock_strike=SAMPLE["reason"])]
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description="Batman backtest (offline)")
    ap.add_argument("--trades", type=int, nargs="*")
    ap.add_argument("--exit-dte", type=int, default=C.EXIT_DTE)
    ap.add_argument("--filter", type=float, default=C.ENTRY_FILTER,
                    help="skip months whose |10-day NIFTY move| at the close before entry is above this %% (e.g. 2.5)")
    ap.add_argument("--out", help="report file (default output/batman/BATMAN_<variant>_backtest_report[_x<N>][_f<X>].xlsx)")
    a = ap.parse_args()
    cyc, strikes = load_cycles(a.trades), load_strikes()
    from shared.calendar import index_move_pct
    mv = index_move_pct(cyc.entry_date, C.TREND_LOOKBACK_DAYS)
    cyc["move_10d_pct"] = [round(mv[d], 2) for d in cyc.entry_date]
    skipped = cyc[cyc.move_10d_pct.abs() > a.filter] if a.filter is not None else cyc.iloc[0:0]
    cyc = cyc.drop(skipped.index)
    rows, daily = [], []
    for t in cyc.itertuples():
        r, d = run_cycle(t, strikes, a.exit_dte)
        rows.append(r)
        daily += d
    allr = pd.DataFrame(rows)
    tr = allr[allr.status == "run"].copy()
    notrun = allr[allr.status != "run"][["trade_id", "entry_date", "expiry", "status"]]
    if not len(tr):
        raise SystemExit("No cycle could be run - download the candles first (strategies/batman/scripts/download.py).")
    tr["year"] = pd.to_datetime(tr.entry_date).dt.year
    tr.insert(4, "move_10d_pct", tr.trade_id.map(dict(zip(cyc.trade_id, cyc.move_10d_pct))))
    S = summary(tr)
    S.loc[0, "value"] = len(cyc) + len(skipped)
    if a.filter is not None:
        S = pd.concat([S.iloc[:1], pd.DataFrame([("Skipped by the 10-day filter", f"{len(skipped)} (|move| > {a.filter}%)")],
                                                 columns=S.columns), S.iloc[1:]], ignore_index=True)
    by_year = tr.groupby("year").agg(trades=("net_rs", "size"), net_rs=("net_rs", "sum"), wins=("net_rs", lambda s: (s > 0).sum()),
                                     targets=("exit_reason", lambda s: (s == "TARGET").sum()),
                                     stops=("exit_reason", lambda s: (s == "STOPLOSS").sum()), worst_rs=("net_rs", "min")).round()
    readme = pd.DataFrame({"Batman backtest": [
        (f"Variant {C.VARIANT}: per side buy {C.BUY_LOTS} lot ~{C.BUY_DELTA:.2f} delta, sell {C.SELL_LOTS} lots ~{C.SELL_DELTA:.2f} delta (further out), calls and puts."
         if not C.WING_OFFSET else
         f"Variant {C.VARIANT}: per side buy {C.BUY_LOTS} lot ~{C.BUY_DELTA:.2f} delta, sell {C.SELL_LOTS} lots {C.SELL_OFFSET} pts further out, buy "
         f"{C.WING_LOTS} lot {C.WING_OFFSET} pts beyond the bought leg (capped loss), calls and puts."),
        ("Entry Monday 11:16 at 43 DTE (the condor's dates), every month, no filter." if a.filter is None else
         f"Entry Monday 11:16 at 43 DTE (the condor's dates); month skipped if |NIFTY 10-day move| > {a.filter}% at the close before entry "
         "(NSE official closes; see sheet Skipped).") + " Strikes by Black-Scholes delta at 11:16 (nearest).",
        "One check a day at 15:16 on the whole position, entry day included; stop before target. Target / stop = 4% of the capital "
        + (f"(static Rs {C.STATIC_CAPITAL:,} = Rs {C.STATIC_CAPITAL * 0.04:,.0f})" if C.CAPITAL_MODE == "static" else
           f"used by the trade, estimated as {C.MARGIN_K:.3f} x NIFTY at 11:16 x lot size (k from the user's StockMock sample)")
        + f"; else time exit at {a.exit_dte} DTE.",
        ("Size: 2 + 1 lots per side at each expiry's lot size. UNHEDGED: one sold lot per side is uncovered (unlimited risk)."
         if not C.WING_OFFSET else "Size: 1 + 2 + 1 lots per side at each expiry's lot size; the far wing caps the loss on each side."),
        "Prices: Breeze 1-minute closes (EXACT = candle at that minute; FFILL/STALE = earlier candle). Costs approximate "
        "(shared/config.py COSTS; each lot counted as an order).",
        "A loss can pass the stop: with one check a day the position is only closed at the next 15:16.",
        "Sheets: Summary, By year, Trades (legs, prices, credit, exit, P&L), Daily (every 15:16 check), Not run, StockMock check (sample trade)."]})
    out = Path(a.out) if a.out else C.OUTPUT_DIR / (f"BATMAN_{C.VARIANT}_backtest_report"
                                                    + ("" if a.exit_dte == C.EXIT_DTE else f"_x{a.exit_dte}")
                                                    + ("" if a.filter is None else f"_f{a.filter:g}")
                                                    + ("_static" if C.CAPITAL_MODE == "static" else "") + ".xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out) as w:
        readme.to_excel(w, sheet_name="Read me", index=False)
        S.to_excel(w, sheet_name="Summary", index=False)
        by_year.to_excel(w, sheet_name="By year")
        tr.drop(columns=["status"]).to_excel(w, sheet_name="Trades", index=False)
        pd.DataFrame(daily).to_excel(w, sheet_name="Daily", index=False)
        notrun.to_excel(w, sheet_name="Not run", index=False)
        if a.filter is not None:
            skipped[["trade_id", "entry_date", "expiry", "move_10d_pct"]].to_excel(w, sheet_name="Skipped", index=False)
        stockmock_check(tr, strikes).to_excel(w, sheet_name="StockMock check", index=False)
    print(S.to_string(index=False))
    print(by_year.to_string())
    if len(notrun):
        print(f"Not run: {notrun.trade_id.tolist()}")
    print(f"Report saved: {out}")


if __name__ == "__main__":
    main()
