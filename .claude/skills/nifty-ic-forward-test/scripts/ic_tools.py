#!/usr/bin/env python3
"""Forward-test helpers for the NIFTY monthly iron condor.

Run from the repo root (the folder that contains ic/config.py):

    python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py rules
    python .../ic_tools.py filter [--entry-date YYYY-MM-DD] [--source auto|nse|csv] [--closes-file F]
    python .../ic_tools.py plan --expiry YYYY-MM-DD [--holiday YYYY-MM-DD ...]
    python .../ic_tools.py check --trade-id N --sce P --bce P --spe P --bpe P
                                 [--date D] [--open X --prev-close Y] [--log]
    python .../ic_tools.py export-ref --trade-id N

All strategy numbers come from ic/config.py, so the README/config stay the single
source of truth. Nothing here calls Breeze or Kite and nothing places orders.

NIFTY daily closes come from NSE's public daily index file (one small CSV per trading day,
https://archives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv); data/nifty_daily.csv
is only a fallback when NSE cannot be reached.
"""
import argparse
import csv
import datetime as dt
import os
import sys
import time
import urllib.error
import urllib.request

REQUIRED = ["SKIP_IF_10D_MOVE_PCT", "TREND_LOOKBACK_DAYS", "HEDGE_WIDTH", "TP_FRACTION",
            "SL_FRACTION", "EXIT_DTE", "ENTRY_DTE", "EXPIRY_WEEKDAY", "ENTRY_TIME", "CHECK_TIME"]
OPTIONAL = ["GAP_UP_EXIT_PCT", "MUHURAT_DAYS", "EXTRA_HOLIDAYS"]
JOURNAL_TRADES = "journal/forward_trades.csv"
JOURNAL_DAILY = "journal/forward_daily.csv"
DAILY_COLS = ["date", "trade_id", "sell_ce", "buy_ce", "sell_pe", "buy_pe", "pnl_pts",
              "pnl_pct_of_credit", "action", "gap_pct", "gap_flag", "nifty_open", "prev_close"]
ENTRY_PX = ("paper_px_sell_ce", "paper_px_buy_ce", "paper_px_sell_pe", "paper_px_buy_pe")
EXIT_PX = ("exit_px_sell_ce", "exit_px_buy_ce", "exit_px_sell_pe", "exit_px_buy_pe")
NSE_INDEX_URL = "https://archives.nseindia.com/content/indices/ind_close_all_{:%d%m%Y}.csv"
NSE_INDEX_NAME = "nifty 50"
NSE_MAX_LOOKBACK_DAYS = 45      # calendar days searched for the trading days needed
NSE_TRIES = 3
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_config():
    sys.path.insert(0, os.getcwd())
    try:
        from ic import config
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Cannot import ic.config ({e}). Run this from the repo root.")
    missing = [n for n in REQUIRED if not hasattr(config, n)]
    if missing:
        sys.exit(f"ic/config.py has no {missing}. Constant names changed? Update REQUIRED in ic_tools.py.")
    return config


def d(s):
    return dt.date.fromisoformat(str(s)[:10])


def as_dates(values):
    out = set()
    for v in values or []:
        try:
            out.add(d(v))
        except Exception:  # noqa: BLE001
            pass
    return out


def read_csv_rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def pick(row, *names):
    low = {k.strip().lower(): v for k, v in row.items()}
    for n in names:
        if n in low:
            return low[n]
    return None


def load_closes_csv(path="data/nifty_daily.csv"):
    if not os.path.exists(path):
        sys.exit(f"{path} not found.")
    out = []
    for r in read_csv_rows(path):
        ds, cl = pick(r, "date", "datetime", "timestamp"), pick(r, "close")
        if ds and cl:
            out.append((d(ds), float(cl)))
    out.sort()
    return out


def nse_close(day):
    """NIFTY 50 close from NSE's daily index file; None if NSE has no file for that day
    (weekend, holiday, or today's file not published yet - it appears in the evening)."""
    req = urllib.request.Request(NSE_INDEX_URL.format(day), headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(NSE_TRIES):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            raise
        except OSError:                              # timeout / connection reset: try again
            if attempt == NSE_TRIES - 1:
                raise
            time.sleep(2)
    if not text.lstrip().lower().startswith("index name"):
        return None
    for row in csv.DictReader(text.splitlines()):
        if (row.get("Index Name") or "").strip().lower() == NSE_INDEX_NAME:
            return float(row["Closing Index Value"])
    return None


def load_closes_nse(before, count):
    """The last `count` NIFTY closes strictly before `before`, oldest first. Every calendar day is
    tried, so special sessions (Muhurat, a Saturday session) count as they do in the backtest data."""
    out, day = [], before
    for _ in range(NSE_MAX_LOOKBACK_DAYS):
        day -= dt.timedelta(days=1)
        c = nse_close(day)
        if c is not None:
            out.append((day, c))
            if len(out) == count:
                break
    return out[::-1]


def get_closes(before, count, source="auto", closes_file=None):
    """(closes, source used). `auto` = NSE website, else the local CSV with a warning."""
    if closes_file:
        return [c for c in load_closes_csv(closes_file) if c[0] < before][-count:], closes_file
    if source in ("auto", "nse"):
        try:
            closes = load_closes_nse(before, count)
        except Exception as e:  # noqa: BLE001
            closes, err = [], str(e)
        else:
            err = "no index files found"
        if len(closes) == count:
            return closes, "NSE daily index files"
        if source == "nse":
            sys.exit(f"Could not get {count} NIFTY closes from NSE ({err}).")
        print(f"WARNING: NSE not reachable ({err}); falling back to data/nifty_daily.csv "
              "(refresh it with `python download.py --index`).")
    return [c for c in load_closes_csv() if c[0] < before][-count:], "data/nifty_daily.csv"


def holidays(cfg, extra):
    hol = as_dates(getattr(cfg, "EXTRA_HOLIDAYS", [])) | as_dates(getattr(cfg, "MUHURAT_DAYS", []))
    return hol | {d(h) for h in extra}


def is_td(day, hol):
    # Weekdays minus known holidays/Muhurat days. Future NSE holidays must be passed via --holiday.
    return day.weekday() < 5 and day not in hol


def time_exit_date(cfg, expiry, hol):
    day = expiry - dt.timedelta(days=int(cfg.EXIT_DTE))
    while not is_td(day, hol):
        day -= dt.timedelta(days=1)
    return day


def cmd_rules(cfg, a):
    for n in REQUIRED + OPTIONAL:
        v = getattr(cfg, n, "(not set)")
        if n in ("MUHURAT_DAYS", "EXTRA_HOLIDAYS") and hasattr(v, "__len__"):
            v = f"{len(v)} dates"
        print(f"{n:22} {v}")
    gap = getattr(cfg, "GAP_UP_EXIT_PCT", None)
    print("gap-up exit:", f"ON at >= {gap}%" if gap else "OFF (log-only)")


def cmd_filter(cfg, a):
    # Same definition as the backtest (ic/common.py trend_moves): last close before the entry day
    # vs the close TREND_LOOKBACK_DAYS trading days earlier.
    n = int(cfg.TREND_LOOKBACK_DAYS)
    before = d(a.entry_date) if a.entry_date else dt.date.today() + dt.timedelta(days=1)
    closes, src = get_closes(before, n + 1, a.source, a.closes_file)
    if len(closes) <= n:
        sys.exit("Not enough NIFTY history for the lookback.")
    (d0, c0), (d1, c1) = closes[0], closes[-1]
    move = (c1 / c0 - 1) * 100
    lim = cfg.SKIP_IF_10D_MOVE_PCT
    verdict = "SKIP" if (lim and abs(move) > float(lim)) else "TRADE"
    print(f"source: {src}")
    print(f"NIFTY close {c1:.2f} on {d1} vs {c0:.2f} on {d0} ({n} trading days earlier)")
    print(f"move = {move:+.2f}%  limit = +/-{lim}%  ->  {verdict}")
    if a.entry_date:
        print(f"valid for an entry on {before} (closes before that day)")
        if (before - d1).days > 4:
            print(f"WARNING: latest close is {d1}, more than 4 days before the entry date - check the data.")
    else:
        print(f"valid for an entry on the next trading day after {d1}; on the entry day itself pass "
              "--entry-date so that day's own close is never used")
        if (dt.date.today() - d1).days > 4:
            print(f"WARNING: latest close is {d1} - stale data, do not judge on it.")
    if a.show:
        for day, c in closes:
            print(f"  {day} {day:%a}  {c:.2f}")


def entry_date(cfg, exp, hol):
    """(entry day, note). ENTRY_DTE calendar days before the normal expiry weekday of the expiry week,
    moved to the next trading day if that day is a holiday."""
    want = WEEKDAYS.index(str(cfg.EXPIRY_WEEKDAY)[:3].title())
    nominal, note = exp, ""
    if exp.weekday() != want:
        nominal = exp + dt.timedelta(days=want - exp.weekday())
        note = (f"expiry is a {exp:%a}, not a {cfg.EXPIRY_WEEKDAY}. If it was only moved for a holiday, the entry "
                f"below keeps the usual pattern. If NSE changed the expiry day, update ENTRY_DTE and "
                f"EXPIRY_WEEKDAY in ic/config.py first.")
    day = nominal - dt.timedelta(days=int(cfg.ENTRY_DTE))
    while not is_td(day, hol):
        day += dt.timedelta(days=1)
    return day, note


def cmd_plan(cfg, a):
    exp = d(a.expiry)
    hol = holidays(cfg, a.holiday)
    ex = time_exit_date(cfg, exp, hol)
    en, note = entry_date(cfg, exp, hol)
    print(f"expiry {exp} ({exp:%a})")
    if note:
        print(f"NOTE: {note}")
    print(f"entry: {en} ({en:%a}) at {cfg.ENTRY_TIME} = {(exp - en).days} DTE "
          f"(rule: {cfg.ENTRY_DTE} DTE for {cfg.EXPIRY_WEEKDAY} expiries; next trading day if a holiday)")
    print(f"time exit: expiry - {cfg.EXIT_DTE}d -> last trading day on/before = {ex} ({ex:%a}) at {cfg.CHECK_TIME}")
    print(f"hedge width {cfg.HEDGE_WIDTH} pts. Evening before entry: run `filter --entry-date {en}`.")
    print("Pass --holiday for any NSE holiday not yet in config.")


def find_trade(tid):
    if not os.path.exists(JOURNAL_TRADES):
        sys.exit(f"{JOURNAL_TRADES} missing. Copy assets/forward_trades_template.csv there first.")
    for r in read_csv_rows(JOURNAL_TRADES):
        if r["trade_id"] == str(tid):
            return r
    sys.exit(f"trade_id {tid} not found in {JOURNAL_TRADES}")


def cmd_check(cfg, a):
    t = find_trade(a.trade_id)
    today = d(a.date) if a.date else dt.date.today()
    e = [float(t[k]) for k in ENTRY_PX]
    credit = e[0] + e[2] - e[1] - e[3]
    now = [a.sce, a.bce, a.spe, a.bpe]
    to_close = now[0] + now[2] - now[1] - now[3]
    pnl = credit - to_close
    pct = pnl / credit * 100 if credit else float("nan")
    tp, sl = float(cfg.TP_FRACTION) * credit, -float(cfg.SL_FRACTION) * credit
    ex = time_exit_date(cfg, d(t["expiry"]), holidays(cfg, a.holiday))

    if a.open is not None and not a.prev_close:      # previous close from NSE when not given
        prev, _ = get_closes(today, 1)
        if prev:
            a.prev_close = prev[-1][1]
            print(f"previous close {a.prev_close:.2f} on {prev[-1][0]}")
    gap_pct = (a.open / a.prev_close - 1) * 100 if (a.open is not None and a.prev_close) else None
    gap_lim = getattr(cfg, "GAP_UP_EXIT_PCT", None)
    threshold = float(gap_lim) if gap_lim else 1.0  # log threshold when the rule is off
    gap_flag = gap_pct is not None and gap_pct >= threshold
    entry_day = today == d(t["entry_date"])
    gap_rule_on = bool(gap_lim) and not entry_day

    # README order: stop-loss -> target -> time exit; gap-up exit only if switched on.
    if pnl <= sl:
        action = "STOPLOSS"
    elif pnl >= tp:
        action = "TARGET"
    elif today >= ex:
        action = "TIME"
    elif gap_rule_on and gap_flag:
        action = "GAP_UP"
    else:
        action = "HOLD"

    print(f"trade {a.trade_id} on {today}: credit {credit:.2f}  cost-to-close {to_close:.2f}  "
          f"P&L {pnl:+.2f} pts ({pct:+.0f}% of credit)")
    print(f"target {tp:+.2f}, stop {sl:+.2f}, time exit date {ex}")
    if gap_pct is not None:
        state = "ON" if gap_rule_on else "OFF - log only"
        print(f"gap {gap_pct:+.2f}% vs prev close; gap-up >= {threshold}%: {'YES' if gap_flag else 'no'} "
              f"(rule {state}{', entry day' if entry_day else ''})")
    print(f"ACTION: {action}")
    if a.log:
        os.makedirs("journal", exist_ok=True)
        new = not os.path.exists(JOURNAL_DAILY)
        with open(JOURNAL_DAILY, "a", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            if new:
                w.writerow(DAILY_COLS)
            w.writerow([today, a.trade_id, *now, f"{pnl:.2f}", f"{pct:.1f}", action,
                        "" if gap_pct is None else f"{gap_pct:.2f}", int(gap_flag),
                        "" if a.open is None else a.open, a.prev_close or ""])
        print(f"logged to {JOURNAL_DAILY}")


def cmd_export_ref(cfg, a):
    t = find_trade(a.trade_id)
    if any(not t.get(k) for k in ("exit_date", *EXIT_PX)):
        sys.exit("Fill exit_date and the four exit_px_* columns for this trade first.")
    e, x = [float(t[k]) for k in ENTRY_PX], [float(t[k]) for k in EXIT_PX]
    pnl = (e[0] + e[2] - e[1] - e[3]) - (x[0] + x[2] - x[1] - x[3])
    print("# append to data/reference/ic_reference_trades.csv")
    print("trade_id,entry_date,entry_time,expiry,sell_ce,buy_ce,sell_pe,buy_pe,qty_stockmock,"
          "ref_exit_date,ref_exit_reason,ref_pnl_pts,ref_pnl_rs,ref_note")
    print(f"{t['trade_id']},{t['entry_date']},{t['entry_time']},{t['expiry']},{t['sell_ce']},{t['buy_ce']},"
          f"{t['sell_pe']},{t['buy_pe']},{t.get('lot_qty', '')},{t['exit_date']},{t.get('exit_reason', '')},"
          f"{pnl:.2f},,forward test paper fills")
    print("\n# append to data/reference/ic_reference_legs.csv")
    print("trade_id,side,opt_type,strike,expiry,entry_dt,exit_dt,entry_px,exit_px")
    for (side, typ, key), i in zip([("SELL", "CE", "sell_ce"), ("BUY", "CE", "buy_ce"),
                                    ("SELL", "PE", "sell_pe"), ("BUY", "PE", "buy_pe")], range(4)):
        print(f"{t['trade_id']},{side},{typ},{t[key]},{t['expiry']},{t['entry_date']} {t['entry_time']},"
              f"{t['exit_date']} {cfg.CHECK_TIME},{e[i]},{x[i]}")
    print("\nPrint-only: review, then paste into the reference files yourself.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("rules")
    x = s.add_parser("filter")
    x.add_argument("--entry-date", help="planned entry day; closes before it are used (default: latest close)")
    x.add_argument("--source", choices=["auto", "nse", "csv"], default="auto")
    x.add_argument("--closes-file", help="CSV with date,close columns (e.g. saved from a broker connector)")
    x.add_argument("--show", action="store_true", help="list the closes used")
    x = s.add_parser("plan")
    x.add_argument("--expiry", required=True)
    x.add_argument("--holiday", action="append", default=[])
    x = s.add_parser("check")
    x.add_argument("--trade-id", required=True)
    for k in ("sce", "bce", "spe", "bpe"):
        x.add_argument(f"--{k}", type=float, required=True)
    x.add_argument("--date")
    x.add_argument("--open", type=float)
    x.add_argument("--prev-close", type=float)
    x.add_argument("--holiday", action="append", default=[])
    x.add_argument("--log", action="store_true")
    x = s.add_parser("export-ref")
    x.add_argument("--trade-id", required=True)
    a = p.parse_args()
    cfg = load_config()
    {"rules": cmd_rules, "filter": cmd_filter, "plan": cmd_plan,
     "check": cmd_check, "export-ref": cmd_export_ref}[a.cmd](cfg, a)


if __name__ == "__main__":
    main()
