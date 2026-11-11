"""Put credit spread trade detail workbook (forward-test rulebook, 20-delta sold put, 200-pt and 300-pt hedges).

Every month the rulebook trades a put spread (2021-26 official set from output/iron_condor/combined_ic_plus_put20_spread.xlsx,
plus 2019-20), with legs, entry/exit prices, credit, target/stop, exit reason, P&L and the daily 15:16 path.
Run from the repo root:  python strategies/iron_condor/analysis/pcs_trade_detail.py
"""
import sys
from datetime import date
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
import numpy as np
import pandas as pd
from strategies.iron_condor.analysis import rulebook_sim as p7
from strategies.iron_condor import config as C, engine as E
from strategies.iron_condor.common import contract_key, cache_file, load_calendar, time_exit_day, lot_size

C.EXIT_DTE = 18
TP, SL = 0.50, 1.00
OUT = "output/iron_condor/pcs_trade_details.xlsx"
# hedge prices corrected by hand (stale zero-volume quotes): (trade, width, strike) -> price at entry
OVERRIDE = {(38, 300, 20650): (91.15, "CORRECTED (stale 114.50, zero volume; midway 20700/20600 PE)")}
# months whose put prices are not usable (shown, but left out of every total)
NOT_TESTABLE = {2004: "NOT TESTABLE – Apr-2020 (COVID): only 8000/7500 PE traded normally; 7800 PE 9 trades, 7700 PE 3 trades, 7700 priced above "
                      "7800 (impossible), 7800 PE 196 → 280 intraday with NIFTY flat. Results built on these prints are meaningless."}


def vol_at(key, d, t):
    """(volume in the entry minute, volume for the whole day)."""
    f = cache_file(key, d)
    if not f.exists():
        return None, None
    c = pd.read_csv(f)
    c = c[c.datetime.astype(str).str.startswith(str(d))]
    r = c[c.datetime.astype(str).str[11:16] == t]
    return (int(r.volume.iloc[0]) if len(r) else 0), int(c.volume.sum())


def run(tid, e, x, legs, q, entry_time="11:16", override=None):
    """legs = [(pos, strike)] puts. Returns trade dict + daily path (same logic as ic/spread_sim.py)."""
    exp = str(x); override = override or {}
    keys = [(p, k, contract_key(exp, k, "PE")) for p, k in legs]
    ent, qual = {}, {}
    for p, k, key in keys:
        if k in override:
            ent[k], qual[k] = override[k][0], override[k][1]
        else:
            px, qq, m = E.price_at(key, e, entry_time)
            if px is None or (qq == "AFTER" and abs(m) > C.MAX_AFTER_MIN_AT_ENTRY):
                return None, None
            ent[k], qual[k] = px, qq
    cr = -sum(p * ent[k] for p, k, _ in keys)
    cal = load_calendar(e, x); tx = time_exit_day(x, cal)
    exit_day, reason, val, xp, path = tx, "TIME", None, None, []
    for d in [z for z in cal if e <= z <= tx]:   # entry day included, as in ic/engine.py
        now = {}
        for p, k, key in keys:
            px, qq, _ = E.price_at(key, d, C.CHECK_TIME)
            now[k] = (px, qq)
        if any(v[0] is None for v in now.values()):
            path.append(dict(trade_id=tid, date=d, note="leg price missing - check skipped"))
            continue
        v = sum(-p * now[k][0] for p, k, _ in keys)       # cost to close
        pnl = cr - v
        row = dict(trade_id=tid, date=d, sold_px=now[legs[0][1]][0], sold_q=now[legs[0][1]][1],
                   bought_px=now[legs[1][1]][0], bought_q=now[legs[1][1]][1], spread_value=round(v, 2),
                   pnl_pts=round(pnl, 2), pnl_pct_of_credit=round(pnl / cr * 100, 1), pnl_rs=round(pnl * q))
        hit = None
        if pnl <= -SL * cr: hit = "STOPLOSS"
        elif pnl >= TP * cr: hit = "TARGET"
        row["event"] = hit or ""
        path.append(row); val, xp = v, now
        if hit:
            exit_day, reason = d, hit
            break
    if val is None:
        return None, None
    pnl = cr - val
    fills = [("SELL" if p < 0 else "BUY", ent[k]) for p, k, _ in keys]
    cost = E.order_costs(fills, q, True) + E.order_costs(fills, q, False)
    s, b = legs[0][1], legs[1][1]
    t = dict(sold_strike=s, bought_strike=b, width=s - b,
             entry_date=e, entry_time=entry_time,
             sold_entry_px=ent[s], sold_entry_quality=qual[s], sold_entry_min_volume=vol_at(contract_key(exp, s, "PE"), e, entry_time)[0],
             sold_day_volume=vol_at(contract_key(exp, s, "PE"), e, entry_time)[1],
             bought_entry_px=ent[b], bought_entry_quality=qual[b], bought_entry_min_volume=vol_at(contract_key(exp, b, "PE"), e, entry_time)[0],
             bought_day_volume=vol_at(contract_key(exp, b, "PE"), e, entry_time)[1],
             credit_pts=round(cr, 2), credit_rs=round(cr * q), target_pts=round(TP * cr, 2), stop_pts=round(SL * cr, 2),
             max_loss_pts=round(s - b - cr, 2), max_loss_rs=round((s - b - cr) * q),
             time_exit_day=tx, exit_date=exit_day, exit_time=C.CHECK_TIME, exit_reason=reason,
             sold_exit_px=xp[s][0], bought_exit_px=xp[b][0], exit_spread_value=round(val, 2),
             pnl_pts=round(pnl, 2), pnl_pct_of_credit=round(pnl / cr * 100, 1),
             gross_rs=round(pnl * q, 2), costs_rs=round(cost, 2), net_rs=round(pnl * q - cost, 2),
             days_held=(exit_day - e).days)
    return t, path


def months():
    """(period, trade_id, entry, expiry, move, mv5, why, sold 20-delta put) for every rulebook put-spread month."""
    T = pd.read_excel("output/iron_condor/combined_ic_plus_put20_spread.xlsx", sheet_name="Trades")
    pc = T[(T.in_totals == "yes") & T.structure_200.astype(str).str.startswith("PCS")]
    out = []
    for r in pc.itertuples():
        e, x, spot, mv, mv5, ce, pe, p20 = p7.month(int(r.trade_id))
        out.append(("2021-26", int(r.trade_id), e, x, mv, mv5, r.why, p20))
    for t in [t for t in p7.REF.index if t >= 1900]:
        d = p7.rulebook(t, lambda s: (400, 300, 200))
        if d["trade"].startswith("PCS"):
            e, x, spot, mv, mv5, ce, pe, p20 = p7.month(t)
            why = "C/W < 40%" if abs(mv) <= 2 else ("rise > 2.5%" if mv > 2.5 else ("fall < -2.5%" if mv < -2.5 else "move 2-2.5%"))
            out.append(("2019-20", t, e, x, mv, mv5, why, p20))
    return out


def main():
    trades, paths = [], {200: [], 300: []}
    for per, tid, e, x, mv, mv5, why, p20 in months():
        q = lot_size(x)
        for w in (200, 300):
            sb = p7.side(str(x), "PE", int(p20), w, e, x)
            base = dict(period=per, trade_id=tid, expiry=x, structure=f"PCS 20Δ/{w}-pt", official="yes" if w == 200 else "alternative (300-pt)",
                        why_no_condor=why, move_10d_pct=round(mv, 2), move_5d_pct=round(mv5, 2), rule_sold_put=int(p20), lot=q)
            if not sb:
                trades.append(dict(base, note="no usable price at entry (fallback rule found none)")); continue
            ov = {k: v for (t_, w_, k), v in OVERRIDE.items() if t_ == tid and w_ == w}
            t, path = run(tid, e, x, [(-1, sb[0]), (1, sb[1])], q, override=ov)
            if t is None:
                trades.append(dict(base, note="not priceable")); continue
            note = []
            if (sb[0], sb[1]) != (int(p20), int(p20) - w):
                note.append(f"fallback strikes (rule {int(p20)}/{int(p20) - w})")
            if ov: note.append("hedge entry price corrected – see bought_entry_quality")
            if tid in NOT_TESTABLE:
                base["official"] = "NOT TESTABLE – not in totals"; note.append(NOT_TESTABLE[tid])
            trades.append(dict(base, **t, note="; ".join(note)))
            for r in path: r.update(period=per, structure=f"PCS {w}")
            paths[w] += path
    # Apr-2026 expiry: rule trades it but 16-Mar is not priceable – indicative entry 24-Mar 15:16, outside totals
    for w, b in ((200, 21800), (300, 21700)):
        x = date(2026, 4, 28); q = lot_size(x)
        t, path = run(2603, date(2026, 3, 24), x, [(-1, 22000), (1, b)], q, entry_time="15:16")
        trades.append(dict(period="2021-26", trade_id=2603, expiry=x, structure=f"PCS 20Δ/{w}-pt",
                           official="INDICATIVE – not in totals", why_no_condor="fall < -2.5%", move_10d_pct=-9.20, move_5d_pct=-5.31,
                           rule_sold_put=22000, lot=q, **t,
                           note="rule entry 16-Mar-26 11:16 not priceable (hedges untraded until 23-Mar, 23-Mar bad print); entry 24-Mar 15:16 used"))
        for r in path: r.update(period="2021-26 (indicative)", structure=f"PCS {w}")
        paths[w] += path
    D = pd.DataFrame(trades).sort_values(["entry_date", "structure"], na_position="last")

    def summ(df):
        g = df.dropna(subset=["net_rs"])
        rows = []
        for (per, st), h in g.groupby(["period", "structure"]):
            s = h.sort_values("entry_date").net_rs; eq = s.cumsum(); dd = (eq - eq.cummax().clip(lower=0)).min()
            w, l = s[s > 0], s[s <= 0]
            rows.append(dict(period=per, structure=st, trades=len(s), net_rs=round(s.sum()), wins=len(w), losses=len(l),
                             targets=int((h.exit_reason == "TARGET").sum()), stops=int((h.exit_reason == "STOPLOSS").sum()),
                             time_exits=int((h.exit_reason == "TIME").sum()), max_dd_rs=round(dd), worst_rs=round(s.min()),
                             avg_credit_pts=round(h.credit_pts.mean(), 1), avg_days_held=round(h.days_held.mean(), 1)))
        return pd.DataFrame(rows)
    official = D[~D.official.str.startswith(("INDICATIVE", "NOT TESTABLE"))]
    S = summ(official)
    readme = pd.DataFrame({"Put credit spread trade details": [
        "Rule: in months the condor does not trade (|10-day move| > 2% or 400-pt condor credit < 160 pts), sell the ~20-delta put and buy the put 200 pts lower",
        "(official) – 300-pt hedge shown as the alternative. Skip the month if the 10-day move > +2.5% and the last 5 days <= +1%.",
        "Entry Monday 11:16 (close of the 11:16 candle). One check a day at 15:16: stop if P&L <= -100% of credit, else target if P&L >= +50% of credit,",
        "else time exit at 15:16 on the last trading day on/before expiry - 18 days. 1 lot. Fallback strikes if a leg has no usable 11:16 price.",
        "Prices: Breeze 1-minute candle closes. Quality EXACT = a candle exists for that minute (it can still have zero volume – see *_min_volume);",
        "FFILL/STALE = last earlier candle; AFTER = first later candle. *_day_volume = contracts traded that day (0 = the price is only a quote).",
        "The 'structure' column is the rule's choice; a 200-pt row can show a 300-pt width when the fallback rule had to widen the hedge (e.g. 1905).",
        "Costs approximate (config.COSTS). Net = gross - costs. Drawdown in entry order.",
        "2021-26 official totals match output/iron_condor/combined_ic_plus_put20_spread.xlsx. Trade 38 (Mar-2024) 300-pt hedge price corrected (stale quote).",
        "Trade 2603 (Apr-2026 expiry) is indicative only (entry a week late on data grounds) and is left out of the summary.",
        "Trade 2004 (Apr-2020, COVID) is NOT TESTABLE – its 7700/7800 PE prices are a few odd trades (see note) – left out of the summary.",
        "Lot sizes: 75 for expiries up to Jun-2021 (NSE circular FAOP47854; ic/config.py fixed 29-Oct-2026).",
        "Trade 2003 (Mar-2020 crash) has no usable entry price. The 15:16 check runs on the entry day too (as in ic/engine.py).",
        "Sheets: Summary, Trades (one row per trade and width), Daily_200 / Daily_300 (every 15:16 check)."]})
    with pd.ExcelWriter(OUT) as wr:
        readme.to_excel(wr, sheet_name="Read me", index=False)
        S.to_excel(wr, sheet_name="Summary", index=False)
        D.to_excel(wr, sheet_name="Trades", index=False)
        pd.DataFrame(paths[200]).to_excel(wr, sheet_name="Daily_200", index=False)
        pd.DataFrame(paths[300]).to_excel(wr, sheet_name="Daily_300", index=False)
    print(S.to_string()); print("saved", OUT, len(D), "rows")
    return D


if __name__ == "__main__":
    main()
