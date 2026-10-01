"""
Export the option prices of every leg of every trade, day by day from entry to exit.

Uses the current rules (hedge width, fallback strikes, exits). Every trade is exported - also the
months the trend filter skips (column `filter_status`), so they can be analysed too; for those the
exit is where the trade would have ended without the filter.

Run:  python export_prices.py [--trades 1 2 3] [--out output/IC_leg_prices.xlsx]
"""
import argparse

import pandas as pd

from ic import config as C
from ic import engine as E
from ic.common import load_calendar, load_inputs, trend_moves
from ic.fallback import choose

LEG_NAMES = {("SELL", "CE"): "sell_CE", ("BUY", "CE"): "buy_CE", ("SELL", "PE"): "sell_PE", ("BUY", "PE"): "buy_PE"}


def day_ohlc(key, day):
    s = E.candles(key, day)
    if s is None or not len(s):
        return dict(day_open=None, day_high=None, day_low=None, day_close=None, minutes_traded=0)
    return dict(day_open=s.iloc[0], day_high=s.max(), day_low=s.min(), day_close=s.iloc[-1], minutes_traded=len(s))


def main():
    ap = argparse.ArgumentParser(description="Export daily option prices of every trade leg")
    ap.add_argument("--trades", type=int, nargs="*")
    ap.add_argument("--out", default=str(C.OUTPUT_DIR / "IC_leg_prices.xlsx"))
    a = ap.parse_args()

    trades, legs = load_inputs(a.trades)
    cal = load_calendar(trades.entry_date.min().date(), trades.expiry.max().date())
    nifty = pd.read_csv(C.INDEX_DAILY["NIFTY"], parse_dates=["date"]).set_index("date").close \
        if C.INDEX_DAILY["NIFTY"].exists() else None
    moves = trend_moves(trades.entry_date) if nifty is not None else None

    wide, long, summary = [], [], []
    for t in trades.itertuples():
        tl, note = legs[legs.trade_id == t.trade_id], ""
        if C.FALLBACK_STRIKES:
            tl, note, _ = choose(t, tl)
        mv = moves[t.entry_date] if moves is not None else None
        status = ("skipped by trend filter" if C.SKIP_IF_10D_MOVE_PCT is not None and mv is not None
                  and abs(mv) > C.SKIP_IF_10D_MOVE_PCT else "taken")
        row, mtm, _, run_status = E.run_trade(t, tl, cal)
        summary.append(dict(trade_id=t.trade_id, entry_date=t.entry_date.date(), expiry=t.expiry.date(),
                            filter_status=status, nifty_10d_move_pct=None if mv is None else round(mv, 2),
                            strike_note=note, exit_date=row["exit_date"] if row else None,
                            exit_reason=row["exit_reason"] if row else run_status,
                            credit=row["credit"] if row else None, pnl_pts=row["pnl_pts"] if row else None,
                            net_pnl=row["net_pnl"] if row else None, qty=int(t.qty)))
        if not row:
            continue
        actions = {m["day"]: m for m in mtm}
        days = [t.entry_date.date()] + [d for d in cal if t.entry_date.date() < d <= row["exit_date"]]
        for d in days:
            tm = C.ENTRY_TIME if d == t.entry_date.date() else C.CHECK_TIME
            w = dict(trade_id=t.trade_id, filter_status=status, date=d, time=tm, dte=(t.expiry.date() - d).days,
                     nifty_close=None if nifty is None or pd.Timestamp(d) not in nifty.index else nifty[pd.Timestamp(d)])
            for r in tl.itertuples():
                name = LEG_NAMES[(r.side, r.opt_type)]
                px, q, m = E.price_at(r.key, d, tm)
                w[f"{name}_strike"], w[f"{name}_price"] = int(r.strike), px
                long.append(dict(trade_id=t.trade_id, filter_status=status, date=d, time=tm, leg=name,
                                 strike=int(r.strike), expiry=t.expiry.date(), price=px, quality=q,
                                 minutes_off=m, **day_ohlc(r.key, d)))
            if d == t.entry_date.date():
                w.update(position_value=row["credit"], pnl_pts=0.0, pnl_pct_credit=0.0, action="ENTRY")
            elif d in actions:
                x = actions[d]
                w.update(position_value=x["value"], pnl_pts=x["pnl_pts"], pnl_pct_credit=x["pnl_pct"], action=x["action"])
            order = [c for n in ("sell_CE", "buy_CE", "sell_PE", "buy_PE") for c in (f"{n}_strike", f"{n}_price")]
            wide.append({**{k: v for k, v in w.items() if k not in order}, **{k: w.get(k) for k in order}})

    with pd.ExcelWriter(a.out, engine="openpyxl") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="Trades", index=False)
        wd = pd.DataFrame(wide)
        tail = ["position_value", "pnl_pts", "pnl_pct_credit", "action"]
        wd[[c for c in wd.columns if c not in tail] + tail].to_excel(xw, sheet_name="Daily_by_trade", index=False)
        pd.DataFrame(long).to_excel(xw, sheet_name="Daily_by_leg", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(max(10, max(len(str(c.value or "")) for c in col[:40]) + 2), 40)
    print(f"{len(summary)} trades, {len(wide)} trade-days, {len(long)} leg-days -> {a.out}")
