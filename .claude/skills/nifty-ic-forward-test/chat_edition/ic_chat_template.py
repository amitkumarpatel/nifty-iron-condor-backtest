#!/usr/bin/env python3
"""
NIFTY iron condor forward test - CHAT EDITION (Claude chat / mobile).

Standalone: Python standard library only, no repository, no internet. The rule values are built in (CONFIG below,
written by chat_edition/build_chat_skill.py from the repo's strategies/iron_condor/config.py). The user (or a read-only
Kite connector) supplies the market data; every result ends with a journal line to copy, because a chat keeps no files.

Commands
  rules                                        rule set and built-in values
  plan    --expiry YYYY-MM-DD                  entry day and time-exit day
  filter  --last C --five C --ten C            10-day / 5-day move and the verdict (closes: last close before entry,
                                               5 and 10 trading days earlier); or --closes "d:c,d:c,..." (11+ closes)
  strikes --expiry D --spot S --chain FILE     picks strikes from a pasted option chain, prices the condors / put spread,
          [--time "YYYY-MM-DD HH:MM"] [--move X --move5 Y]   applies the rules, prints the journal line
  check   --row "<journal line>" --now "sce,bce,spe,bpe" [--date D] [--open O --prev-close P]
          (or --expiry D --entry-date D --strikes "sce,bce,spe,bpe" --entry-px "sce,bce,spe,bpe" instead of --row;
           leave the CE values 0 / empty for a put credit spread)
Chain file: CSV with header strike,ce_bid,ce_ask,ce_ltp,pe_bid,pe_ask,pe_ltp (blank = no quote).
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import sys

# ---- BUILT-IN VALUES (generated - do not edit by hand; rebuild with build_chat_skill.py) ----
CONFIG = json.loads(r'''__CONFIG_JSON__''')
# ---- end of generated values ----

C = CONFIG
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
JOURNAL_COLS = C["journal_cols"]
MAX_SPREAD_FRACTION = 0.25


def d(s):
    return dt.date.fromisoformat(str(s).strip()[:10])


def holidays(extra=()):
    return {d(x) for x in C["holidays"] + C["muhurat_days"]} | {d(x) for x in extra}


def is_td(day, hol):
    return day.weekday() < 5 and day not in hol


def time_exit_date(expiry, hol):
    day = expiry - dt.timedelta(days=C["exit_dte"])
    while not is_td(day, hol):
        day -= dt.timedelta(days=1)
    return day


def lot_size(expiry):
    return next(q for last, q in C["lot_sizes"] if expiry <= d(last))


# ---- Black-Scholes (same as shared/options_math.py) ----
def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, vol, opt):
    r, q = C["risk_free_rate"], C["div_yield"]
    d1 = (math.log(S / K) + (r - q + vol * vol / 2) * T) / (vol * math.sqrt(T))
    d2 = d1 - vol * math.sqrt(T)
    if opt == "CE":
        return S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2), math.exp(-q * T) * _ncdf(d1)
    return K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1), -math.exp(-q * T) * _ncdf(-d1)


def implied_vol(px, S, K, T, opt):
    lo, hi = 0.01, 3.0
    if not bs(S, K, T, lo, opt)[0] < px < bs(S, K, T, hi, opt)[0]:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bs(S, K, T, mid, opt)[0] < px else (lo, mid)
    return (lo + hi) / 2


# ---- rules ----
def wide_label():
    return " and ".join(f"{w}-pt" for w in C["fwd_wide_widths"])


def rule_lines():
    w, n = C["fwd_signal_width"], C["hedge_width"]
    rich, floor = C["fwd_wide_min_credit_pct"] * w / 100, C["fwd_min_credit_pct"] * w / 100
    pw = "/".join(map(str, C["fwd_pcs_widths"]))
    return [
        f"Entry Monday {C['entry_time']}, {C['entry_dte']} DTE before a {C['expiry_weekday']} expiry (next trading day if a holiday); "
        f"sold legs ~{C['target_delta']:.2f} delta.",
        f"Evening before: 10-day move = last NSE close before entry vs the close {C['lookback']} trading days earlier.",
        f"At {C['entry_time']}: credit test = net credit of the {w}-pt condor.",
        f"1. |move| <= {C['fwd_wide_move_pct']}% and credit >= {rich:.0f} pts ({C['fwd_wide_min_credit_pct']:.0f}% of {w}) -> "
        f"{wide_label()} condor, target {C['fwd_wide_tp']:.0%} of credit.",
        f"2. else |move| <= {C['fwd_narrow_move_pct']}% and credit >= {floor:.0f} pts ({C['fwd_min_credit_pct']:.0f}%) -> "
        f"{n}-pt condor, target {C['tp']:.0%}.",
        f"3. else -> put credit spread: sell ~{C['fwd_pcs_delta']:.2f}-delta put, buy {pw} pts lower, target {C['fwd_pcs_tp']:.0%} "
        f"of its credit - but SKIP the month if the 10-day move > +{C['fwd_pcs_rise_pct']}% and the 5-day move <= "
        f"+{C['fwd_pcs_min_5d_pct']}%.",
        f"All: stop {C['sl']:.0%} of credit, one check a day at {C['check_time']}, time exit on the last trading day on/before "
        f"expiry - {C['exit_dte']} days; 1 lot; no adjustments or re-entry.",
        f"Shadow log: earlier rule = {n}-pt condor if |move| <= {C['earlier_limit_pct']}%; also the "
        f"{'/'.join(map(str, C['fwd_pcs_alt_widths']))}-pt put spread.",
    ]


def fwd_band(move):
    m, w = abs(move), C["fwd_signal_width"]
    rich, floor = C["fwd_wide_min_credit_pct"] * w / 100, C["fwd_min_credit_pct"] * w / 100
    if m <= C["fwd_narrow_move_pct"]:
        return (f"TRADE - width decided at {C['entry_time']} by the {w}-pt condor credit: >= {rich:.0f} pts -> {wide_label()}, "
                f"{floor:.0f}-{rich:.0f} pts -> {C['hedge_width']}-pt, below {floor:.0f} -> no condor (put spread check)")
    if m <= C["fwd_wide_move_pct"]:
        return f"TRADE ONLY IF RICH - {wide_label()} if the {w}-pt credit >= {rich:.0f} pts, else no condor (put spread check)"
    return f"NO CONDOR - 10-day move beyond +/-{C['fwd_wide_move_pct']}% (put spread check below)"


def fwd_decide(move, credit):
    m, w = abs(move), C["fwd_signal_width"]
    ratio = credit / w * 100
    if m <= C["fwd_wide_move_pct"] and ratio >= C["fwd_wide_min_credit_pct"]:
        return list(C["fwd_wide_widths"]), f"move {move:+.2f}% and credit {ratio:.1f}% >= {C['fwd_wide_min_credit_pct']:.0f}%"
    if m <= C["fwd_narrow_move_pct"] and ratio >= C["fwd_min_credit_pct"]:
        return [C["hedge_width"]], f"move {move:+.2f}%, credit {ratio:.1f}% (between {C['fwd_min_credit_pct']:.0f}% and {C['fwd_wide_min_credit_pct']:.0f}%)"
    if m > C["fwd_wide_move_pct"]:
        return [], f"move {move:+.2f}% beyond +/-{C['fwd_wide_move_pct']}%"
    return [], f"credit {ratio:.1f}% below the {C['fwd_min_credit_pct']:.0f}% floor" if ratio < C["fwd_min_credit_pct"] else \
        f"move {move:+.2f}% needs credit >= {C['fwd_wide_min_credit_pct']:.0f}%, it is {ratio:.1f}%"


def pcs_decide(move, move5):
    if move > C["fwd_pcs_rise_pct"] and move5 <= C["fwd_pcs_min_5d_pct"]:
        return False, f"10-day rise {move:+.2f}% but 5-day only {move5:+.2f}% (<= +{C['fwd_pcs_min_5d_pct']}%: rally stalled)"
    return True, f"10-day move {move:+.2f}%, 5-day {move5:+.2f}%"


def tp_fraction(width):
    return C["fwd_wide_tp"] if width >= min(C["fwd_wide_widths"]) else C["tp"]


def near(x, line, tol):
    return abs(abs(x) - line) <= tol


# ---- commands ----
def cmd_rules(a):
    print(f"NIFTY IC forward test - chat edition, values built {C['built']} from the repo config")
    for line in rule_lines():
        print("  " + line)
    yrs = sorted({d(h).year for h in C["holidays"]})
    print(f"Lot size for a new expiry: {C['lot_sizes'][-1][1]}. NSE holiday lists built in for {yrs}.")
    if dt.date.today().year not in yrs or (dt.date.today().month == 12 and dt.date.today().year + 1 not in yrs):
        print("WARNING: holiday list may be missing the coming year - rebuild the skill after NSE publishes it.")


def cmd_plan(a):
    exp, hol = d(a.expiry), holidays(a.holiday)
    want = WEEKDAYS.index(C["expiry_weekday"][:3].title())
    nominal = exp + dt.timedelta(days=want - exp.weekday()) if exp.weekday() != want else exp
    en = nominal - dt.timedelta(days=C["entry_dte"])
    while not is_td(en, hol):
        en += dt.timedelta(days=1)
    ex = time_exit_date(exp, hol)
    print(f"expiry {exp} ({exp:%a}); lot size {lot_size(exp)}")
    if exp.weekday() != want:
        print(f"NOTE: expiry is a {exp:%a}, not a {C['expiry_weekday']} (holiday move?). Entry keeps the usual pattern.")
    print(f"entry {en} ({en:%a}) at {C['entry_time']} = {(exp - en).days} DTE")
    print(f"time exit {ex} ({ex:%a}) at {C['check_time']} (expiry - {C['exit_dte']} days, previous trading day if needed)")
    yrs = {d(h).year for h in C["holidays"]}
    if not {en.year, ex.year} <= yrs:
        print(f"WARNING: no NSE holiday list built in for {sorted({en.year, ex.year} - yrs)} - check NSE's holiday page.")
    print(f"evening before {en}: run filter with the last close before {en}.")


def cmd_filter(a):
    if a.closes:
        pts = sorted((d(x.split(":")[0]), float(x.split(":")[1])) for x in a.closes.split(",") if x.strip())
        if len(pts) < C["lookback"] + 1:
            sys.exit(f"need {C['lookback'] + 1} closes (last close + {C['lookback']} before it); got {len(pts)}")
        pts = pts[-(C["lookback"] + 1):]
        last, five, ten = pts[-1][1], pts[-6][1], pts[0][1]
        print(f"closes used: last {pts[-1][0]} {last:.2f}, 5 days earlier {pts[-6][0]} {five:.2f}, "
              f"10 days earlier {pts[0][0]} {ten:.2f}")
    else:
        if a.last is None or a.ten is None:
            sys.exit("give --last and --ten (and --five), or --closes")
        last, five, ten = a.last, a.five, a.ten
    move = (last / ten - 1) * 100
    move5 = (last / five - 1) * 100 if five else None
    print(f"10-day move = {move:+.2f}%" + (f"   5-day move = {move5:+.2f}%" if move5 is not None else ""))
    print(f"FORWARD-TEST RULE: {fwd_band(move)}")
    if move5 is not None:
        ok, why = pcs_decide(move, move5)
        print(f"  if the condor is skipped: {'PUT CREDIT SPREAD' if ok else 'SKIP THE MONTH'} - {why}")
    else:
        print("  put-spread check needs the 5-day move (--five)")
    print(f"earlier rule (shadow log): {'SKIP' if abs(move) > C['earlier_limit_pct'] else str(C['hedge_width']) + '-pt condor'}")
    for line in (C["fwd_wide_move_pct"], C["fwd_narrow_move_pct"], C["fwd_pcs_rise_pct"]):
        if near(move, line, 0.1):
            print(f"CLOSE CALL: the 10-day move is within 0.1 of {line}% - confirm both closes are NSE's OFFICIAL closes.")
            break
    print(f"journal: filter_move_pct={move:.2f}" + (f", move_5d_pct={move5:.2f}" if move5 is not None else ""))


def read_chain(path):
    text = open(path).read() if path != "-" else sys.stdin.read()
    rows = list(csv.DictReader(io.StringIO(text.strip())))
    def num(v):
        try:
            v = float(str(v).replace(",", "").strip())
            return v if v > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0
    out = {}
    for r in rows:
        r = {k.strip().lower(): v for k, v in r.items() if k}
        k = int(float(r["strike"]))
        for opt in ("ce", "pe"):
            out[(k, opt.upper())] = dict(strike=k, opt=opt.upper(), bid=num(r.get(f"{opt}_bid")),
                                         ask=num(r.get(f"{opt}_ask")), last=num(r.get(f"{opt}_ltp")))
    return out


def price(q):
    bid, ask, last = q["bid"], q["ask"], q["last"]
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        if ask - bid <= MAX_SPREAD_FRACTION * mid:
            return mid, ""
        return (last, "WIDE bid-ask - last price") if bid <= last <= ask else (mid, "WIDE bid-ask")
    return (last, "NO BID/ASK - last price") if last > 0 else (None, "NO PRICE")


def cmd_strikes(a):
    exp = d(a.expiry)
    ts = dt.datetime.strptime(a.time, "%Y-%m-%d %H:%M") if a.time else dt.datetime.combine(dt.date.today(), dt.time(11, 16))
    T = (dt.datetime.combine(exp, dt.time(15, 30)) - ts) / dt.timedelta(days=365)
    spot, chain = a.spot, read_chain(a.chain)
    for q in chain.values():
        q["px"], q["flag"] = price(q)
        iv = implied_vol(q["px"], spot, q["strike"], T, q["opt"]) if q["px"] else None
        q["delta"] = abs(bs(spot, q["strike"], T, iv, q["opt"])[1]) if iv else None
    qty = lot_size(exp)
    print(f"expiry {exp}, {(exp - ts.date()).days} DTE, quotes at {ts:%d-%b-%Y %H:%M}, NIFTY {spot:.2f}, lot {qty}")

    def best(opt, target):
        side = 1 if opt == "CE" else -1
        otm = [q for q in chain.values() if q["opt"] == opt and q["delta"] and (q["strike"] - spot) * side > 0]
        return min(otm, key=lambda q: abs(q["delta"] - target)) if otm else None

    def ok_pair(s_, b_):
        return s_ and b_ and s_["px"] and b_["px"] and b_["px"] < s_["px"]

    def spread(opt, target, width):
        side = 1 if opt == "CE" else -1
        b = best(opt, target)
        if b is None:
            return None, f"{opt}: no priced out-of-the-money strikes"
        tries = [(b["strike"], b["strike"] + side * width, "")]
        tries += [(b["strike"] + side * s, b["strike"] + side * (s + width), f"spread {abs(s)} pts {'closer' if s < 0 else 'further out'}")
                  for s in C["fallback_shifts"]]
        tries += [(b["strike"], b["strike"] + side * (width + e), f"hedge widened to {width + e}") for e in C["fallback_hedge_extra"]]
        for ks, kb, why in tries:
            s_, b_ = chain.get((ks, opt)), chain.get((kb, opt))
            if ok_pair(s_, b_):
                return (s_, b_), (f"{opt}: {b['strike']}/{b['strike'] + side * width} not usable -> {ks}/{kb} ({why})" if why else "")
        return None, f"{opt}: no usable hedge price near {b['strike']} ({width}-pt) - check the chain"

    def show(title, legs, width, tpf):
        print(f"\n{title}")
        print("  leg      strike   delta     bid     ask   price  note")
        for name, q in legs:
            dl = f"{q['delta']:.3f}" if q["delta"] else "  -  "
            print(f"  {name:8} {q['strike']:6d}  {dl}  {q['bid']:7.2f} {q['ask']:7.2f} {q['px']:7.2f}  {q['flag']}")
        cr = sum((q["px"] if n.startswith("sell") else -q["px"]) for n, q in legs)
        worst = sum((q["bid"] if n.startswith("sell") else -q["ask"]) for n, q in legs)
        wd = max(abs(legs[i][1]["strike"] - legs[i + 1][1]["strike"]) for i in range(0, len(legs), 2))
        print(f"  credit {cr:.2f} pts = {cr / width * 100:.1f}% of {width}; at bid/ask {worst:.2f} (slippage {cr - worst:.2f})")
        print(f"  target +{tpf * cr:.2f} pts ({tpf:.0%}), stop -{C['sl'] * cr:.2f}, max loss {wd - cr:.2f} pts; "
              f"Rs credit {cr * qty:,.0f}, Rs max loss {(wd - cr) * qty:,.0f}")
        return cr

    sig, narrow, wides = C["fwd_signal_width"], C["hedge_width"], C["fwd_wide_widths"]
    built = {}
    for w in sorted(set(wides + [narrow, sig])):
        ce, nce = spread("CE", C["target_delta"], w)
        pe, npe = spread("PE", C["target_delta"], w)
        built[w] = (None if not (ce and pe) else [("sell_ce", ce[0]), ("buy_ce", ce[1]), ("sell_pe", pe[0]), ("buy_pe", pe[1])],
                    [n for n in (nce, npe) if n])
    credits = {}
    for w, (legs, notes) in built.items():
        for n in notes:
            print(f"NOTE {w}-pt: {n}")
        if legs:
            credits[w] = sum((q["px"] if n.startswith("sell") else -q["px"]) for n, q in legs)
    ladder = [credits[w] for w in sorted(credits)]
    if any(x >= y for x, y in zip(ladder, ladder[1:])):
        print("WARNING: credit does not rise with width - a stale/bad price is likely; check the hedge strikes.")

    print("\n=== Decision ===")
    widths, move, move5 = None, a.move, a.move5
    if move is None:
        print("10-day move not given (--move) - decision left open.")
    elif sig not in credits:
        print(f"{sig}-pt condor cannot be priced - decide by hand from the broker chain.")
    else:
        widths, why = fwd_decide(move, credits[sig])
        print(f"10-day move {move:+.2f}%; {sig}-pt credit {credits[sig]:.2f} pts = {credits[sig] / sig * 100:.1f}% (credit test)")
        print(f"DECISION: {'NO CONDOR' if not widths else '+'.join(map(str, widths)) + '-pt condor'} - {why}")
        for line in (C["fwd_wide_min_credit_pct"], C["fwd_min_credit_pct"]) if abs(move) <= C["fwd_wide_move_pct"] else ():
            if abs(credits[sig] - line * sig / 100) <= 3:
                print(f"CLOSE CALL: credit within 3 pts of {line * sig / 100:.0f} - confirm the leg prices live.")
        print(f"earlier rule (shadow log): {'SKIP' if abs(move) > C['earlier_limit_pct'] else str(narrow) + '-pt condor'}")

    journal = dict(trade_id=f"FT{exp:%y%m}", entry_date=ts.date().isoformat(), entry_time=f"{ts:%H:%M}", expiry=exp.isoformat(), lot_qty=qty,
                   filter_move_pct="" if move is None else f"{move:.2f}", move_5d_pct="" if move5 is None else f"{move5:.2f}",
                   credit_400_pts=f"{credits.get(400, ''):.2f}" if 400 in credits else "",
                   credit_300_pts=f"{credits.get(300, ''):.2f}" if 300 in credits else "",
                   earlier_rule_decision="" if move is None else ("SKIP" if abs(move) > C["earlier_limit_pct"] else f"IC{narrow}"))
    for w, (legs, _) in built.items():
        if legs:
            role = "CHOSEN" if widths and w in widths else ("credit test" if w == sig else "shadow / not chosen")
            show(f"{w}-pt condor ({role})", legs, w, tp_fraction(w))
    chosen = None
    if widths:
        chosen = built[widths[0]][0]
        journal.update(structure="IC", hedge_width=widths[0], rule_decision=f"IC{widths[0]}")
    elif widths == [] or move is None:
        print("\n=== Put credit spread (condor skipped) ===")
        pcs_ok = None
        if move is not None and move5 is not None:
            pcs_ok, why = pcs_decide(move, move5)
            print(f"PUT SPREAD DECISION: {'TRADE' if pcs_ok else 'SKIP THE MONTH'} - {why}")
        else:
            print("needs --move and --move5")
        for w in C["fwd_pcs_widths"] + C["fwd_pcs_alt_widths"]:
            pe, note = spread("PE", C["fwd_pcs_delta"], w)
            if not pe:
                print(f"{w}-pt put spread: {note}")
                continue
            if note:
                print(f"NOTE: {note}")
            role = ("CHOSEN" if pcs_ok else "would be") if w in C["fwd_pcs_widths"] else "shadow log"
            cr = show(f"{w}-pt put spread ({role})", [("sell_pe", pe[0]), ("buy_pe", pe[1])], w, C["fwd_pcs_tp"])
            journal[f"pcs_credit_{w}_pts"] = f"{cr:.2f}"
            if w in C["fwd_pcs_widths"] and pcs_ok:
                chosen = [("sell_pe", pe[0]), ("buy_pe", pe[1])]
                journal.update(structure="PCS", hedge_width=w, rule_decision=f"PCS{w}")
        if pcs_ok is False:
            journal.update(structure="", rule_decision="SKIP")
    if chosen:
        for n, q in chosen:
            journal[n] = q["strike"]
            journal[f"paper_px_{n}"] = f"{q['px']:.2f}"
            journal[f"bidask_{n}"] = f"{q['bid']:.2f}/{q['ask']:.2f}"
    print("\nThese are the strikes the rules point to, not an instruction to trade. Confirm live prices in the broker.")
    print("JOURNAL LINE (keep it; paste it back for the daily check):")
    print(",".join(JOURNAL_COLS))
    print(",".join(str(journal.get(c, "")).replace(",", ";") for c in JOURNAL_COLS))


def floats(s, n=4):
    v = [float(x) if str(x).strip() else 0.0 for x in str(s).split(",")]
    if len(v) != n:
        sys.exit(f"expected {n} comma-separated values (sell_ce,buy_ce,sell_pe,buy_pe), got {s!r}")
    return v


def cmd_check(a):
    if a.row:
        line = a.row.strip()
        vals = next(csv.reader([line]))
        if vals and vals[0] == "trade_id":
            sys.exit("paste the data line, not the header")
        t = dict(zip(JOURNAL_COLS, vals + [""] * (len(JOURNAL_COLS) - len(vals))))
        exp, entry_day = d(t["expiry"]), d(t["entry_date"])
        strikes = [float(t[k] or 0) for k in ("sell_ce", "buy_ce", "sell_pe", "buy_pe")]
        e = [float(t[f"paper_px_{k}"] or 0) for k in ("sell_ce", "buy_ce", "sell_pe", "buy_pe")]
        tid = t.get("trade_id", "")
    else:
        if not (a.expiry and a.entry_date and a.strikes and a.entry_px):
            sys.exit("give --row, or --expiry --entry-date --strikes --entry-px")
        exp, entry_day, strikes, e, tid = d(a.expiry), d(a.entry_date), floats(a.strikes), floats(a.entry_px), ""
    today = d(a.date) if a.date else dt.date.today()
    now = floats(a.now)
    pcs = strikes[0] == 0
    credit = e[0] + e[2] - e[1] - e[3]
    pnl = credit - (now[0] + now[2] - now[1] - now[3])
    if pcs:
        width, tpf = strikes[2] - strikes[3], C["fwd_pcs_tp"]
    else:
        width = max(strikes[1] - strikes[0], strikes[2] - strikes[3])
        tpf = tp_fraction(width)
    tp, sl = tpf * credit, -C["sl"] * credit
    ex = time_exit_date(exp, holidays(a.holiday))
    gap = (a.open / a.prev_close - 1) * 100 if (a.open and a.prev_close) else None
    gap_flag = gap is not None and gap >= 1.0
    action = "STOPLOSS" if pnl <= sl else "TARGET" if pnl >= tp else "TIME" if today >= ex else "HOLD"
    qty = lot_size(exp)
    print(f"{'put credit spread' if pcs else f'{width:.0f}-pt condor'}, entry {entry_day}, expiry {exp}, lot {qty}")
    print(f"{today}: credit {credit:.2f}  P&L {pnl:+.2f} pts ({pnl / credit * 100:+.0f}% of credit) = Rs {pnl * qty:+,.0f}")
    print(f"target {tp:+.2f} ({tpf:.0%}), stop {sl:+.2f}, time exit {ex}")
    if gap is not None:
        print(f"gap {gap:+.2f}% vs previous close; gap-up >= 1%: {'YES (log it - exit rule is OFF)' if gap_flag else 'no'}")
    print(f"ACTION: {action}" + ("  -> close all legs at the 15:16 prices" if action != "HOLD" else ""))
    print("DAILY JOURNAL LINE: date,trade_id,sell_ce,buy_ce,sell_pe,buy_pe,pnl_pts,pnl_pct_of_credit,action,gap_pct,gap_flag")
    print(",".join(map(str, [today, tid, *now, f"{pnl:.2f}", f"{pnl / credit * 100:.1f}", action,
                             "" if gap is None else f"{gap:.2f}", int(gap_flag)])))


def main():
    ap = argparse.ArgumentParser(description="NIFTY IC forward test - chat edition")
    s = ap.add_subparsers(dest="cmd", required=True)
    s.add_parser("rules")
    x = s.add_parser("plan")
    x.add_argument("--expiry", required=True)
    x.add_argument("--holiday", action="append", default=[])
    x = s.add_parser("filter")
    x.add_argument("--last", type=float)
    x.add_argument("--five", type=float)
    x.add_argument("--ten", type=float)
    x.add_argument("--closes", help='"YYYY-MM-DD:close,..." - at least 11 closes ending with the last close before entry')
    x = s.add_parser("strikes")
    x.add_argument("--expiry", required=True)
    x.add_argument("--spot", type=float, required=True)
    x.add_argument("--chain", required=True, help="CSV file (or - for stdin)")
    x.add_argument("--time", help='"YYYY-MM-DD HH:MM" of the quotes (default today 11:16)')
    x.add_argument("--move", type=float)
    x.add_argument("--move5", type=float)
    x = s.add_parser("check")
    x.add_argument("--row")
    x.add_argument("--expiry")
    x.add_argument("--entry-date")
    x.add_argument("--strikes")
    x.add_argument("--entry-px")
    x.add_argument("--now", required=True)
    x.add_argument("--date")
    x.add_argument("--open", type=float)
    x.add_argument("--prev-close", type=float)
    x.add_argument("--holiday", action="append", default=[])
    a = ap.parse_args()
    {"rules": cmd_rules, "plan": cmd_plan, "filter": cmd_filter, "strikes": cmd_strikes, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
