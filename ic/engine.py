"""
Engine: replay the StockMock iron condor trades on Breeze 1-minute data (offline,
reads data_cache/). Rules: enter 4 legs at 11:16, check combined P&L once a day at 15:16,
exit all legs on TP (50% of credit), SL (100% of credit) or the 15-DTE time exit.
No intraday monitoring, no adjustments, no re-entry, 1 lot at each period's lot size.

Run:  python backtest.py                 (all trades)
      python backtest.py --trades 1 2 3
Output: output/IC_backtest_report.xlsx (Summary, Trades, Daily_MTM, Reconciliation, Data_Quality)
"""
import argparse
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ic import config as C
from ic.common import load_inputs, load_calendar, time_exit_day, cache_file, trend_moves
from ic.fallback import choose as choose_fallback

EPS = 1e-9


@lru_cache(maxsize=None)
def candles(key: str, day: date) -> pd.Series:
    f = cache_file(key, day)
    if not f.exists():
        return None
    df = pd.read_csv(f)
    if not len(df):
        return pd.Series(dtype=float)
    s = pd.Series(df.close.astype(float).values,
                  index=pd.to_datetime(df.datetime.str[:16])).sort_index()
    return s[~s.index.duplicated(keep="last")]


def price_at(key, day, hhmm):
    """Close of candle labelled hh:mm; else last candle before it that day; else first after.
    Returns (price, quality, minutes_off)."""
    s = candles(key, day)
    if s is None:
        return None, "NOT_DOWNLOADED", None
    target = datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time())
    if target in s.index:
        return float(s[target]), "EXACT", 0
    before = s[s.index < target]
    if len(before):
        m = int((target - before.index[-1]).total_seconds() // 60)
        return float(before.iloc[-1]), ("STALE" if m > C.STALE_WARN_MIN else "FFILL"), m
    after = s[s.index > target]
    if len(after):
        m = int((after.index[0] - target).total_seconds() // 60)
        return float(after.iloc[0]), "AFTER", -m
    return None, "NO_TRADES", None


def order_costs(legs_px, qty, entry: bool):
    """legs_px: list of (side, price). entry=True -> SELL legs sold, BUY legs bought."""
    k = C.COSTS
    sell_turn = buy_turn = 0.0
    for side, px in legs_px:
        turn = px * qty
        is_sell = (side == "SELL") == entry
        if is_sell:
            sell_turn += turn
        else:
            buy_turn += turn
    tot = sell_turn + buy_turn
    brk = k["brokerage_per_order"] * len(legs_px)
    exch = tot * k["exch_txn_pct"] / 100
    sebi = tot * k["sebi_per_crore"] / 1e7
    stt = sell_turn * k["stt_sell_pct"] / 100
    stamp = buy_turn * k["stamp_buy_pct"] / 100
    gst = (brk + exch + sebi) * k["gst_pct"] / 100
    slip = k["slippage_pts_per_leg"] * qty * len(legs_px)
    return brk + exch + sebi + stt + stamp + gst + slip


@lru_cache(maxsize=1)
def _nifty_gaps() -> dict:
    """NIFTY opening gap in % (open vs previous close) per day, from data/nifty_daily.csv."""
    f = Path(C.INDEX_DAILY["NIFTY"])
    if not f.exists():
        raise SystemExit(f"{f} not found - run `python download.py --index` (needed by the gap-up exit), "
                         "or set IC_GAP_UP_EXIT=off.")
    n = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
    if "open" not in n.columns:
        return {}
    g = (n.open / n.close.shift() - 1) * 100
    return {d.date(): v for d, v in g.dropna().items()}


def nifty_gap_pct(day) -> float:
    return _nifty_gaps().get(day, 0.0)


def bad_hedge(px, pairs):
    """True if a bought leg is priced at or above the sold leg of the same type - impossible for a
    further out-of-the-money option, so one of the two prints is a stray illiquid trade."""
    return any(px[b] >= px[s] for s, b in pairs)


def run_trade(t, tlegs, cal):
    entry_day, expiry = t.entry_date.date(), t.expiry.date()
    tx_day = time_exit_day(expiry, cal)
    qty = int(t.qty)
    sign = {r.key: (1 if r.side == "SELL" else -1) for r in tlegs.itertuples()}
    by = {(r.side, r.opt_type): r.key for r in tlegs.itertuples()}
    pairs = [(by["SELL", o], by["BUY", o]) for o in ("CE", "PE") if ("SELL", o) in by and ("BUY", o) in by]
    dq = []

    # ---- entry ----
    entry_px = {}
    for r in tlegs.itertuples():
        px, q, m = price_at(r.key, entry_day, C.ENTRY_TIME)
        if q == "AFTER" and -m > C.MAX_AFTER_MIN_AT_ENTRY:   # first trade came too late to be known at entry
            px, q = None, "AFTER_TOO_LATE"
        if px is None and C.USE_REFERENCE_ENTRY_IF_MISSING and pd.notna(r.entry_px):
            px, q = float(r.entry_px), "REF"
        entry_px[r.key] = px
        dq.append(dict(trade_id=t.trade_id, day=entry_day, check="entry", contract=r.key,
                       quality=q, minutes_off=m, price=px, stockmock_px=r.entry_px))
    if any(v is None for v in entry_px.values()):
        return None, [], dq, "NO_ENTRY_PRICE"
    if bad_hedge(entry_px, pairs):
        return None, [], dq, "BAD_ENTRY_PRICE"
    credit = sum(sign[k] * v for k, v in entry_px.items())
    tp, sl = C.TP_FRACTION * credit, -C.SL_FRACTION * credit

    # ---- daily 15:16 checks ----
    mtm, last_px, exit_info = [], dict(entry_px), None
    for d in [d for d in cal if entry_day <= d <= tx_day]:
        px_now, quals = {}, []
        for r in tlegs.itertuples():
            px, q, m = price_at(r.key, d, C.CHECK_TIME)
            if q == "NOT_DOWNLOADED":                    # never value a trade on a gap in our own download
                return None, mtm, dq, "NOT_DOWNLOADED (run download.py)"
            if px is None and d == tx_day:
                px, q = last_px[r.key], "CARRY"          # forced exit: carry last known price
            px_now[r.key] = px
            quals.append(q)
            if q != "EXACT":
                dq.append(dict(trade_id=t.trade_id, day=d, check="daily", contract=r.key,
                               quality=q, minutes_off=m, price=px, stockmock_px=None))
        if not any(v is None for v in px_now.values()) and bad_hedge(px_now, pairs):
            if d == tx_day:                              # forced exit: carry the last consistent prices
                px_now = {k: last_px[k] for k in px_now}
            else:
                mtm.append(dict(trade_id=t.trade_id, day=d, dte=(expiry - d).days, value=None,
                                pnl_pts=None, pnl_pct=None, action="SKIP (hedge priced >= sold leg)",
                                quality="/".join(sorted(set(quals)))))
                dq.append(dict(trade_id=t.trade_id, day=d, check="daily", contract="hedge vs sold",
                               quality="BAD_PRICE", minutes_off=None, price=None, stockmock_px=None))
                continue
        if any(v is None for v in px_now.values()):
            mtm.append(dict(trade_id=t.trade_id, day=d, dte=(expiry - d).days, value=None,
                            pnl_pts=None, pnl_pct=None, action="SKIP (missing price)",
                            quality="/".join(sorted(set(quals)))))
            continue
        last_px.update(px_now)
        value = sum(sign[k] * v for k, v in px_now.items())
        pnl = credit - value
        if pnl <= sl + EPS:
            action = "STOPLOSS"
        elif pnl >= tp - EPS:
            action = "TARGET"
        elif C.GAP_UP_EXIT_PCT is not None and d > entry_day and nifty_gap_pct(d) >= C.GAP_UP_EXIT_PCT:
            action = "GAP_UP"
        elif d == tx_day:
            action = "TIME"
        else:
            action = "HOLD"
        mtm.append(dict(trade_id=t.trade_id, day=d, dte=(expiry - d).days, value=round(value, 2),
                        pnl_pts=round(pnl, 2), pnl_pct=round(pnl / credit, 4), action=action,
                        quality="/".join(sorted(set(quals)))))
        if action != "HOLD":
            exit_info = (d, action, dict(px_now), value)
            break

    if exit_info is None:
        return None, mtm, dq, "NO_EXIT"
    xd, reason, exit_px, value = exit_info
    pnl_pts = credit - value
    gross = pnl_pts * qty
    legs_list = list(tlegs.itertuples())
    costs = (order_costs([(r.side, entry_px[r.key]) for r in legs_list], qty, True) +
             order_costs([(r.side, exit_px[r.key]) for r in legs_list], qty, False))
    valid = [x["pnl_pts"] for x in mtm if x["pnl_pts"] is not None]
    row = dict(trade_id=t.trade_id, entry_date=entry_day, exit_date=xd, expiry=expiry,
               entry_dte=(expiry - entry_day).days, exit_dte=(expiry - xd).days,
               days_held=len(valid), qty=qty)
    for r in legs_list:
        tag = f"{r.side[0]}{r.opt_type}"          # SCE, BCE, SPE, BPE
        row[f"{tag}_strike"] = int(r.strike)
        row[f"{tag}_entry"] = entry_px[r.key]
        row[f"{tag}_exit"] = exit_px[r.key]
    row.update(credit=round(credit, 2), tp_level=round(tp, 2), sl_level=round(sl, 2),
               exit_value=round(value, 2), pnl_pts=round(pnl_pts, 2), pnl_pct_credit=round(pnl_pts / credit, 4),
               exit_reason=reason, gross_pnl=round(gross, 2), costs=round(costs, 2),
               net_pnl=round(gross - costs, 2), mfe_pts=max(valid), mae_pts=min(valid),
               non_exact_prices=sum(1 for x in dq if x["quality"] != "EXACT"))
    return row, mtm, dq, "OK"


def stats(pnl: pd.Series, pts: pd.Series = None) -> dict:
    p = pnl.reset_index(drop=True)
    eq = np.concatenate([[0], p.cumsum().values])
    mdd = float((eq - np.maximum.accumulate(eq)).min())

    def streak(mask):
        best = cur = 0
        for x in mask:
            cur = cur + 1 if x else 0
            best = max(best, cur)
        return best
    w, l = p[p > 0], p[p <= 0]
    out = {"Trades": len(p), "Total P&L (Rs)": p.sum(), "Avg P&L per trade (Rs)": p.mean(),
           "Max profit (Rs)": p.max(), "Max loss (Rs)": p.min(), "Win %": len(w) / len(p) if len(p) else 0,
           "Winning trades": len(w), "Losing trades": len(l),
           "Avg win (Rs)": w.mean() if len(w) else 0, "Avg loss (Rs)": l.mean() if len(l) else 0,
           "Max drawdown (Rs)": mdd, "Max win streak": streak(p > 0), "Max loss streak": streak(p <= 0),
           "Profit factor": w.sum() / -p[p < 0].sum() if (p < 0).any() else np.inf}
    if pts is not None:
        out["Total P&L (points)"] = pts.sum()
    return out


def max_concurrent(tr: pd.DataFrame) -> int:
    ev = [(d, 1) for d in tr.entry_date] + [(d, -1) for d in tr.exit_date]
    ev.sort(key=lambda x: (x[0], -x[1]))  # same day: entry (11:16) counts before an exit (15:16)
    cur = best = 0
    for _, s in ev:
        cur += s
        best = max(best, cur)
    return best


def main():
    ap = argparse.ArgumentParser(description="Replay the iron condor trades on cached Breeze data")
    ap.add_argument("--trades", type=int, nargs="*", help="only these trade ids")
    ap.add_argument("--out", help="report path (default output/IC_backtest_report.xlsx)")
    a = ap.parse_args()
    trades, legs = load_inputs(a.trades)
    if not C.CACHE_DIR.exists():
        raise SystemExit("No downloaded data found. Run `python download.py` first.")
    cal = load_calendar(trades.entry_date.min().date(), trades.expiry.max().date())
    rows, mtm_all, dq_all, problems, skipped = [], [], [], [], []
    # NIFTY move over TREND_LOOKBACK_DAYS at the close before entry: drives the filter and is shown
    # on every trade (also with the filter off, if data/nifty_daily.csv exists)
    have_index = Path(C.INDEX_DAILY["NIFTY"]).exists()
    moves = trend_moves(trades.entry_date) if (C.SKIP_IF_10D_MOVE_PCT is not None or have_index) else None
    move_col = f"nifty_{C.TREND_LOOKBACK_DAYS}d_move_pct"
    for t in trades.itertuples():
        if C.SKIP_IF_10D_MOVE_PCT is not None:
            mv = moves[t.entry_date]
            if abs(mv) > C.SKIP_IF_10D_MOVE_PCT:
                skipped.append({"trade_id": t.trade_id, "entry_date": t.entry_date.date(), "expiry": t.expiry.date(),
                                move_col: round(mv, 2),
                                "reason": f"|{C.TREND_LOOKBACK_DAYS}-day move| > {C.SKIP_IF_10D_MOVE_PCT}%"})
                continue
        tlegs, note = legs[legs.trade_id == t.trade_id], ""
        if C.FALLBACK_STRIKES:
            tlegs, note, _ = choose_fallback(t, tlegs)
        row, mtm, dq, status = run_trade(t, tlegs, cal)
        mtm_all += mtm
        dq_all += dq
        if row:
            row["strike_note"] = note
            rows.append(row)
        else:
            problems.append((t.trade_id, status))
    if not rows:
        raise SystemExit("No trade could be run: " + ", ".join(f"T{a}={b}" for a, b in problems)
                         + "\nMissing prices? Run `python download.py` with the same settings first.")
    tr = pd.DataFrame(rows).sort_values("trade_id")
    pos = tr.columns.get_loc("entry_dte") + 1
    tr.insert(pos, move_col, [round(moves[pd.Timestamp(d)], 2) if moves is not None else None for d in tr.entry_date])
    tr.insert(pos + 1, "trend_filter", "off" if C.SKIP_IF_10D_MOVE_PCT is None else
              f"pass (|move| <= {C.SKIP_IF_10D_MOVE_PCT}%)")
    mtm = pd.DataFrame(mtm_all)
    dq = pd.DataFrame(dq_all)

    # ---- reconciliation ----
    ref = trades[["trade_id", "ref_exit_date", "ref_exit_reason", "ref_pnl_pts", "ref_pnl_rs", "ref_note"]].copy()
    ref["ref_pnl_rs"] = (trades.ref_pnl_pts * trades.qty).round(0)   # StockMock points at config.LOT_SIZES
    ref["ref_exit_date"] = ref.ref_exit_date.dt.date
    rec = ref.merge(tr[["trade_id", "exit_date", "exit_reason", "credit", "pnl_pts", "gross_pnl"]], on="trade_id", how="left")
    rec["pts_diff"] = (rec.pnl_pts - rec.ref_pnl_pts).round(2)
    rec["rs_diff"] = (rec.gross_pnl - rec.ref_pnl_rs).round(0)
    ref_credit = rec.credit  # engine credit used to judge boundary
    ref_pct = rec.ref_pnl_pts / ref_credit
    boundary = ((ref_pct - C.TP_FRACTION).abs() <= C.BOUNDARY_BAND) | ((ref_pct + C.SL_FRACTION).abs() <= C.BOUNDARY_BAND)

    def status(r, b):
        if r.trade_id in skip_ids:
            return "SKIPPED (filter)"
        if pd.isna(r.exit_date):
            return "NOT RUN"
        same_exit = r.exit_date == r.ref_exit_date and r.exit_reason == r.ref_exit_reason
        if same_exit and abs(r.pts_diff) <= C.RECON_PNL_TOL_PTS:
            return "MATCH"
        if same_exit:
            return "PNL DIFF"
        return "EXIT DIFF"
    skip_ids = {x["trade_id"] for x in skipped}
    rec["status"] = [status(r, b) for r, b in zip(rec.itertuples(), boundary)]
    bad_q = {"REF", "CARRY", "NO_TRADES", "NOT_DOWNLOADED", "STALE", "AFTER", "AFTER_TOO_LATE", "BAD_PRICE"}
    weak = set(dq[dq.quality.isin(bad_q)].trade_id) if len(dq) else set()
    rec["expected?"] = np.select(
        [rec.status == "SKIPPED (filter)",
         rec.ref_note.fillna("").str.contains("manual", case=False),
         rec.status == "NOT RUN",
         (C.HEDGE_WIDTH != C.REF_HEDGE_WIDTH) & (rec.status != "MATCH"),
         (C.EXIT_DTE != C.REF_EXIT_DTE) & (rec.status == "EXIT DIFF") & ((rec.exit_reason == "TIME") | (rec.ref_exit_reason == "TIME")),
         rec.trade_id.isin(weak) & (rec.status != "MATCH"),
         boundary & (rec.status != "MATCH")],
        [f"skipped - NIFTY {C.TREND_LOOKBACK_DAYS}-day move > {C.SKIP_IF_10D_MOVE_PCT}%",
         "yes - manual exit in StockMock",
         "not run - a leg had no price at entry",
         f"yes - hedges {C.HEDGE_WIDTH} pts vs StockMock {C.REF_HEDGE_WIDTH} pts",
         f"yes - exit rule {C.EXIT_DTE} DTE vs StockMock {C.REF_EXIT_DTE} DTE",
         "check Data_Quality - thin/missing prices", "likely - P&L near TP/SL level"],
        default="")

    # ---- summary ----
    s_gross = stats(tr.gross_pnl, tr.pnl_pts)
    s_net = stats(tr.net_pnl)
    r_ = ref.set_index("trade_id").loc[tr.trade_id]
    s_ref = stats(r_.ref_pnl_rs, r_.ref_pnl_pts)
    summ = pd.DataFrame({"Engine (gross)": s_gross, "Engine (net of costs)": s_net, "StockMock (same trades)": s_ref})
    extra = pd.DataFrame({"Engine (gross)": {
        "Exits - TARGET": (tr.exit_reason == "TARGET").sum(),
        "Exits - STOPLOSS": (tr.exit_reason == "STOPLOSS").sum(),
        "Exits - GAP_UP": (tr.exit_reason == "GAP_UP").sum(),
        "Exits - TIME": (tr.exit_reason == "TIME").sum(),
        "Max concurrent positions": max_concurrent(tr),
        "Total costs (Rs)": tr.costs.sum(),
        "Reconciliation MATCH": (rec.status == "MATCH").sum(),
        "Reconciliation PNL DIFF": (rec.status == "PNL DIFF").sum(),
        "Reconciliation EXIT DIFF": (rec.status == "EXIT DIFF").sum(),
        "Trades skipped by trend filter": len(skipped),
        "Trades on fallback strikes": int((tr.strike_note != "").sum()),
        "Trades not run": len(problems),
        "Non-exact prices used": int((dq.quality != "EXACT").sum()) if len(dq) else 0,
    }})
    summ = pd.concat([summ, extra])
    notes = pd.DataFrame({"Notes": [
        f"Rules: entry {C.ENTRY_TIME}, daily check {C.CHECK_TIME}, TP {C.TP_FRACTION:.0%} / SL {C.SL_FRACTION:.0%} of credit, "
        f"time exit on last trading day on/before expiry-{C.EXIT_DTE} (holidays and Muhurat sessions skipped).",
        (f"Entry filter: skip if |NIFTY {C.TREND_LOOKBACK_DAYS}-day move| > {C.SKIP_IF_10D_MOVE_PCT}% at the prior close "
         f"({len(skipped)} trades skipped, see Skipped sheet)." if C.SKIP_IF_10D_MOVE_PCT is not None else "Entry filter: off."),
        (f"Gap-up exit: ON - exit at {C.CHECK_TIME} on a day NIFTY opens >= {C.GAP_UP_EXIT_PCT}% above the previous close."
         if C.GAP_UP_EXIT_PCT is not None else "Gap-up exit: off (IC_GAP_UP_EXIT=1.0 to test)."),
        "Sizing: 1 lot at each expiry's NIFTY lot size (config.LOT_SIZES).",
        "April-2026 expiry cycle not traded (no StockMock data) - not in the reference list.",
        "Max drawdown uses trades in entry order, like StockMock.",
        "Costs are approximate; slippage per leg set in ic_config.COSTS.",
        "Problems: " + (", ".join(f"T{a}={b}" for a, b in problems) if problems else "none"),
    ]})

    out = a.out or C.REPORT_XLSX
    C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="Summary")
        notes.to_excel(xw, sheet_name="Summary", startrow=len(summ) + 3, index=False)
        tr.to_excel(xw, sheet_name="Trades", index=False)
        mtm.to_excel(xw, sheet_name="Daily_MTM", index=False)
        rec.to_excel(xw, sheet_name="Reconciliation", index=False)
        pd.DataFrame(skipped, columns=["trade_id", "entry_date", "expiry", move_col, "reason"]).to_excel(
            xw, sheet_name="Skipped", index=False)
        (dq[dq.quality != "EXACT"] if len(dq) else dq).to_excel(xw, sheet_name="Data_Quality", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                w = max(len(str(c.value)) if c.value is not None else 0 for c in col[:60])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 60)
        xs = xw.book["Summary"]
        for row in xs.iter_rows(min_row=2, max_row=len(summ) + 1, min_col=2, max_col=4):
            for c in row:
                if isinstance(c.value, float):
                    c.number_format = "0.0%" if xs.cell(c.row, 1).value == "Win %" else "#,##0.00"

    # ---- console summary ----
    pd.set_option("display.width", 160)
    print(summ.to_string(float_format=lambda v: f"{v:,.2f}"))
    print("\nReconciliation:", rec.status.value_counts().to_dict())
    diffs = rec[rec.status != "MATCH"]
    if len(diffs):
        print(diffs[["trade_id", "ref_exit_date", "ref_exit_reason", "exit_date", "exit_reason", "ref_pnl_pts", "pnl_pts", "expected?"]].to_string(index=False))
    if problems:
        print("Trades not run:", problems)
    print(f"\nReport saved: {out}")


if __name__ == "__main__":
    main()
