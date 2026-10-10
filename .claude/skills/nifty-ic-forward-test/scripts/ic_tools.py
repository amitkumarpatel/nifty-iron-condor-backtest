#!/usr/bin/env python3
"""Forward-test helpers for the NIFTY monthly iron condor.

Run from the repo root (the folder that contains ic/config.py):

    python .claude/skills/nifty-ic-forward-test/scripts/ic_tools.py rules
    python .../ic_tools.py filter [--entry-date YYYY-MM-DD] [--source auto|nse|csv] [--closes-file F]
    python .../ic_tools.py plan --expiry YYYY-MM-DD [--holiday YYYY-MM-DD ...]
    python .../ic_tools.py holidays [--write]
    python .../ic_tools.py strikes --expiry YYYY-MM-DD [--delta 0.30] [--save FILE]
    python .../ic_tools.py check --trade-id N --sce P --bce P --spe P --bpe P
                                 [--date D] [--open X --prev-close Y] [--log]
    python .../ic_tools.py export-ref --trade-id N

All strategy numbers come from ic/config.py, so the README/config stay the single
source of truth. Nothing here calls Breeze or Kite and nothing places orders.

NIFTY daily closes come from NSE's public daily index file (one small CSV per trading day,
https://archives.nseindia.com/content/indices/ind_close_all_DDMMYYYY.csv); data/nifty_daily.csv
is only a fallback when NSE cannot be reached. `holidays` and `strikes` read NSE's website too
(holiday list and option chain); both are read-only.
"""
import argparse
import csv
import datetime as dt
import http.cookiejar
import json
import re
import os
import sys
import time
import urllib.error
import urllib.request

REQUIRED = ["SKIP_IF_10D_MOVE_PCT", "TREND_LOOKBACK_DAYS", "HEDGE_WIDTH", "TP_FRACTION",
            "SL_FRACTION", "EXIT_DTE", "ENTRY_DTE", "EXPIRY_WEEKDAY", "ENTRY_TIME", "CHECK_TIME"]
OPTIONAL = ["GAP_UP_EXIT_PCT", "MUHURAT_DAYS", "EXTRA_HOLIDAYS", "NSE_HOLIDAYS"]
FWD = ["FWD_WIDE_WIDTH", "FWD_WIDE_MOVE_PCT", "FWD_WIDE_MIN_CREDIT_PCT", "FWD_NARROW_MOVE_PCT",
       "FWD_MIN_CREDIT_PCT", "FWD_WIDE_TP_FRACTION"]
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
NSE_HOME = "https://www.nseindia.com/option-chain"
NSE_HOLIDAY_API = "https://www.nseindia.com/api/holiday-master?type=trading"
NSE_CHAIN_INFO_API = "https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY"
NSE_CHAIN_API = "https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry={}"
NSE_HOLIDAY_SEGMENT = "FO"
NSE_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/126.0 Safari/537.36")
TARGET_DELTA = 0.30             # sold legs (README section 1)
MAX_SPREAD_FRACTION = 0.25      # bid-ask wider than this share of the mid price is flagged WIDE
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_config():
    sys.path.insert(0, os.getcwd())
    try:
        from ic import config
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Cannot import ic.config ({e}). Run this from the repo root.")
    missing = [n for n in REQUIRED + FWD if not hasattr(config, n)]
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
    hol = (as_dates(getattr(cfg, "EXTRA_HOLIDAYS", [])) | as_dates(getattr(cfg, "MUHURAT_DAYS", []))
           | as_dates(getattr(cfg, "NSE_HOLIDAYS", [])))
    return hol | {d(h) for h in extra}


def is_td(day, hol):
    # Weekdays minus known holidays/Muhurat days (config NSE_HOLIDAYS, kept current by `holidays --write`).
    return day.weekday() < 5 and day not in hol


def time_exit_date(cfg, expiry, hol):
    day = expiry - dt.timedelta(days=int(cfg.EXIT_DTE))
    while not is_td(day, hol):
        day -= dt.timedelta(days=1)
    return day


def fwd_text(cfg):
    """The forward-test rule set (ic/config.py FWD_*), as plain lines."""
    w, n = int(cfg.FWD_WIDE_WIDTH), int(cfg.HEDGE_WIDTH)
    rich, floor = cfg.FWD_WIDE_MIN_CREDIT_PCT * w / 100, cfg.FWD_MIN_CREDIT_PCT * w / 100
    return [
        f"1. |10-day move| <= {cfg.FWD_WIDE_MOVE_PCT}% and {w}-pt condor credit >= {rich:.0f} pts ({cfg.FWD_WIDE_MIN_CREDIT_PCT:.0f}% of width)"
        f" -> {w}-pt condor, target {cfg.FWD_WIDE_TP_FRACTION:.0%} of credit",
        f"2. else |10-day move| <= {cfg.FWD_NARROW_MOVE_PCT}% and {w}-pt condor credit >= {floor:.0f} pts ({cfg.FWD_MIN_CREDIT_PCT:.0f}%)"
        f" -> {n}-pt condor, target {cfg.TP_FRACTION:.0%} of credit",
        "3. else skip the month",
        f"both: stop {cfg.SL_FRACTION:.0%} of credit, one check a day at {cfg.CHECK_TIME}, time exit at expiry - {cfg.EXIT_DTE} days",
        f"shadow-log every month: the earlier rule ({n}-pt condor if |10-day move| <= {cfg.SKIP_IF_10D_MOVE_PCT}%)",
    ]


def fwd_band(cfg, move):
    """What the 10-day move alone says the evening before entry."""
    m = abs(move)
    w = int(cfg.FWD_WIDE_WIDTH)
    rich, floor = cfg.FWD_WIDE_MIN_CREDIT_PCT * w / 100, cfg.FWD_MIN_CREDIT_PCT * w / 100
    if m <= cfg.FWD_NARROW_MOVE_PCT:
        return (f"TRADE - width decided at entry by the {w}-pt condor credit: >= {rich:.0f} pts -> {w}-pt, "
                f"{floor:.0f}-{rich:.0f} pts -> {int(cfg.HEDGE_WIDTH)}-pt, below {floor:.0f} pts -> skip")
    if m <= cfg.FWD_WIDE_MOVE_PCT:
        return f"TRADE ONLY IF RICH - {w}-pt condor if its credit is >= {rich:.0f} pts at entry, else skip"
    return f"SKIP - 10-day move beyond +/-{cfg.FWD_WIDE_MOVE_PCT}%"


def fwd_decide(cfg, move, wide_credit):
    """(width or None, reason) under the forward-test rule set."""
    m, w = abs(move), int(cfg.FWD_WIDE_WIDTH)
    ratio = wide_credit / w * 100
    if m <= cfg.FWD_WIDE_MOVE_PCT and ratio >= cfg.FWD_WIDE_MIN_CREDIT_PCT:
        return w, f"move {move:+.2f}% within +/-{cfg.FWD_WIDE_MOVE_PCT}% and credit {ratio:.1f}% >= {cfg.FWD_WIDE_MIN_CREDIT_PCT:.0f}%"
    if m <= cfg.FWD_NARROW_MOVE_PCT and ratio >= cfg.FWD_MIN_CREDIT_PCT:
        return int(cfg.HEDGE_WIDTH), (f"move {move:+.2f}% within +/-{cfg.FWD_NARROW_MOVE_PCT}%, credit {ratio:.1f}% between "
                                      f"{cfg.FWD_MIN_CREDIT_PCT:.0f}% and {cfg.FWD_WIDE_MIN_CREDIT_PCT:.0f}%")
    if m > cfg.FWD_WIDE_MOVE_PCT:
        return None, f"move {move:+.2f}% beyond +/-{cfg.FWD_WIDE_MOVE_PCT}%"
    if ratio < cfg.FWD_MIN_CREDIT_PCT:
        return None, f"credit {ratio:.1f}% below the {cfg.FWD_MIN_CREDIT_PCT:.0f}% floor"
    return None, (f"move {move:+.2f}% between {cfg.FWD_NARROW_MOVE_PCT}% and {cfg.FWD_WIDE_MOVE_PCT}% needs credit >= "
                  f"{cfg.FWD_WIDE_MIN_CREDIT_PCT:.0f}%, it is {ratio:.1f}%")


def tp_fraction(cfg, width):
    return float(cfg.FWD_WIDE_TP_FRACTION) if width >= int(cfg.FWD_WIDE_WIDTH) else float(cfg.TP_FRACTION)


def cmd_rules(cfg, a):
    print("Forward-test rule set (ic/config.py FWD_*):")
    for line in fwd_text(cfg):
        print("  " + line)
    print("\nConfig values:")
    for n in REQUIRED + FWD + OPTIONAL:
        v = getattr(cfg, n, "(not set)")
        if n in ("MUHURAT_DAYS", "EXTRA_HOLIDAYS", "NSE_HOLIDAYS") and hasattr(v, "__len__"):
            v = f"{len(v)} dates"
        print(f"{n:24} {v}")
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
    print(f"10-day move = {move:+.2f}%")
    print(f"FORWARD-TEST RULE: {fwd_band(cfg, move)}")
    print(f"earlier rule (shadow log, {int(cfg.HEDGE_WIDTH)}-pt, limit +/-{lim}%): {verdict}")
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
    known = {h.year for h in as_dates(getattr(cfg, "NSE_HOLIDAYS", []))}
    need = {en.year, ex.year, exp.year} - known
    if need:
        print(f"WARNING: no NSE holiday list in config for {sorted(need)} - run `holidays --write` "
              "(NSE publishes next year's list in December) or pass --holiday.")


def nse_session():
    """URL opener carrying NSE's cookies (its JSON APIs refuse requests without a page visit first)."""
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = [("User-Agent", NSE_UA), ("Accept", "application/json, text/html"),
                     ("Accept-Language", "en-US,en;q=0.9"), ("Referer", NSE_HOME)]
    op.open(NSE_HOME, timeout=25).read()
    return op


def nse_json(op, url):
    for attempt in range(NSE_TRIES):
        try:
            with op.open(url, timeout=25) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except (OSError, ValueError):
            if attempt == NSE_TRIES - 1:
                raise
            time.sleep(2)


def cmd_holidays(cfg, a):
    try:
        rows = nse_json(nse_session(), NSE_HOLIDAY_API)[NSE_HOLIDAY_SEGMENT]
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not read NSE's holiday list ({e}). See "
                 "https://www.nseindia.com/resources/exchange-communication-holidays")
    new = {dt.datetime.strptime(r["tradingDate"], "%d-%b-%Y").date(): " ".join(r["description"].split())
           for r in rows}
    years = sorted({k.year for k in new})
    print(f"NSE trading holidays, {NSE_HOLIDAY_SEGMENT} segment, {years}: {len(new)} days")
    for k in sorted(new):
        print(f"  {k} {k:%a}  {new[k]}{'   (weekend)' if k.weekday() >= 5 else ''}")
    star = [k for k in new if "*" in new[k]]
    if star:
        print(f"NOTE: {', '.join(map(str, star))} is marked * by NSE (Muhurat trading). Check that it is in "
              "MUHURAT_DAYS in ic/config.py.")
    have = as_dates(getattr(cfg, "NSE_HOLIDAYS", []))
    add, gone = sorted(set(new) - have), sorted(k for k in have if k.year in years and k not in new)
    print(f"config NSE_HOLIDAYS: {len(have)} dates; new {len(add)}: {', '.join(map(str, add)) or '-'}; "
          f"no longer listed {len(gone)}: {', '.join(map(str, gone)) or '-'}")
    if not a.write:
        if add or gone:
            print("Run again with --write to update ic/config.py.")
        return
    # keep other years already in config, replace the years NSE just returned
    path = os.path.join("ic", "config.py")
    text = open(path).read()
    block = re.search(r"# NSE_HOLIDAYS_START\n.*?# NSE_HOLIDAYS_END", text, re.S)
    if not block:
        sys.exit("Markers # NSE_HOLIDAYS_START / # NSE_HOLIDAYS_END not found in ic/config.py.")
    old_notes = dict(re.findall(r'"(\d{4}-\d{2}-\d{2})",\s*#\s*\w{3}\s+(.*)', block.group(0)))
    keep = {k: old_notes.get(str(k), "") for k in have if k.year not in years}
    allh = {**keep, **new}
    lines = "".join(f'    "{k}",  # {k:%a} {allh[k]}\n' for k in sorted(allh))
    fetched = f"# fetched from NSE on {dt.date.today()} ({NSE_HOLIDAY_SEGMENT} segment, years {years})"
    text = text.replace(block.group(0), f"# NSE_HOLIDAYS_START\n{fetched}\nNSE_HOLIDAYS = [\n{lines}]\n# NSE_HOLIDAYS_END")
    open(path, "w").write(text)
    print(f"ic/config.py updated: NSE_HOLIDAYS now has {len(allh)} dates. Review `git diff ic/config.py`, "
          "run `python tests/smoke_test.py`, then commit.")


def leg_quote(q):
    """(price used, bid, ask, last, flag) for one option of NSE's chain. Price = mid of bid/ask; when the
    bid-ask is wide, the last traded price if it lies inside the bid-ask; with no bid/ask, the last price."""
    bid, ask, last = (q or {}).get("buyPrice1") or 0, (q or {}).get("sellPrice1") or 0, (q or {}).get("lastPrice") or 0
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        if (ask - bid) <= MAX_SPREAD_FRACTION * mid:
            return mid, bid, ask, last, ""
        if bid <= last <= ask:
            return last, bid, ask, last, "WIDE bid-ask - last traded price used"
        return mid, bid, ask, last, "WIDE bid-ask"
    if last > 0:
        return last, bid, ask, last, "NO BID/ASK - last traded price"
    return None, bid, ask, last, "NO PRICE"


def cmd_strikes(cfg, a):
    from ic.common import lot_size
    from ic.strikes import bs, implied_vol
    exp = d(a.expiry)
    tag = f"{exp:%d-%b-%Y}"
    try:
        op = nse_session()
        listed = nse_json(op, NSE_CHAIN_INFO_API).get("expiryDates", [])
        if tag not in listed:
            sys.exit(f"{tag} is not a listed NIFTY expiry. NSE lists: {', '.join(listed[:8])} ...")
        rec = nse_json(op, NSE_CHAIN_API.format(tag))["records"]
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Could not read NSE's option chain ({e}). Use read-only broker quotes instead.")
    spot = float(rec["underlyingValue"])
    ts = dt.datetime.strptime(rec["timestamp"], "%d-%b-%Y %H:%M:%S")
    T = (dt.datetime.combine(exp, dt.time(15, 30)) - ts) / dt.timedelta(days=365)
    chain = {}
    for row in rec["data"]:
        k = int(row["strikePrice"])
        for opt in ("CE", "PE"):
            px, bid, ask, last, flag = leg_quote(row.get(opt))
            iv = implied_vol(px, spot, k, T, opt) if px else None
            chain[(k, opt)] = dict(strike=k, opt=opt, px=px, bid=bid, ask=ask, last=last, flag=flag,
                                   delta=abs(bs(spot, k, T, iv, opt)[1]) if iv else None)
    age = (dt.datetime.now() - ts).total_seconds() / 60
    print(f"NSE option chain, expiry {exp} ({(exp - ts.date()).days} DTE), snapshot {ts:%d-%b-%Y %H:%M:%S}, NIFTY {spot:.2f}")
    if age > 10:
        print(f"WARNING: snapshot is {age:.0f} minutes old (market closed or NSE delay) - not entry prices.")

    def build(width, show):
        """Legs for one hedge width: {opt: (sold, hedge)}, notes; None if a side has no usable price."""
        legs, notes = {}, []
        for opt, out_ in (("CE", 1), ("PE", -1)):
            otm = [q for q in chain.values() if q["opt"] == opt and q["delta"] and (q["strike"] - spot) * out_ > 0]
            if not otm:
                sys.exit(f"No priced out-of-the-money {opt} strikes in the chain.")
            best = min(otm, key=lambda q: abs(q["delta"] - a.delta))
            if show:
                print(f"\n{opt} strikes near {a.delta:.2f} delta:")
                print("  strike   delta      bid      ask     last   note")
                for q in sorted(otm, key=lambda q: abs(q["delta"] - a.delta))[:5]:
                    print(f"  {q['strike']:6d}  {q['delta']:6.3f} {q['bid']:8.2f} {q['ask']:8.2f} {q['last']:8.2f}   "
                          f"{'<- closest' if q is best else ''} {q['flag']}")
            # README fallback: a hedge with no usable price (or priced >= the sold leg) moves the whole spread
            # by FALLBACK_SHIFTS (negative = closer to the money), else the hedge is widened.
            tries = [(best["strike"], best["strike"] + out_ * width, "")]
            tries += [(best["strike"] + out_ * s_, best["strike"] + out_ * (s_ + width),
                       f"spread {abs(s_)} pts {'closer' if s_ < 0 else 'further out'}") for s_ in cfg.FALLBACK_SHIFTS]
            tries += [(best["strike"], best["strike"] + out_ * (width + e), f"hedge widened to {width + e} pts")
                      for e in cfg.FALLBACK_HEDGE_EXTRA]
            for ks, kb, why in tries:
                s_, b_ = chain.get((ks, opt)), chain.get((kb, opt))
                if s_ and b_ and s_["px"] and b_["px"] and b_["bid"] > 0 and b_["ask"] > 0 and b_["px"] < s_["px"]:
                    legs[opt] = (s_, b_)
                    if why:
                        notes.append(f"{opt}: {best['strike']}/{best['strike'] + out_ * width} has no usable hedge "
                                     f"price -> {ks}/{kb} ({why})")
                    break
            else:
                return None, [f"{opt}: no usable hedge price for {best['strike']} or its fallback strikes ({width}-pt)"]
        return legs, notes

    def credit_of(legs):
        (sc, bc), (sp, bp) = legs["CE"], legs["PE"]
        return sc["px"] + sp["px"] - bc["px"] - bp["px"]

    def report(width, legs, notes, tp_frac, title):
        rows = [("sell_ce", legs["CE"][0]), ("buy_ce", legs["CE"][1]), ("sell_pe", legs["PE"][0]), ("buy_pe", legs["PE"][1])]
        print(f"\n{title} ({a.delta:.2f} delta sold, hedges {width} pts out):")
        print("  leg      strike    delta      bid      ask    price   note")
        for name, q in rows:
            dl = f"{q['delta']:6.3f}" if q["delta"] else "     -"
            print(f"  {name:8} {q['strike']:6d}   {dl} {q['bid']:8.2f} {q['ask']:8.2f} {q['px']:8.2f}   {q['flag']}")
        for n in notes:
            print(f"NOTE: {n}")
        (sc, bc), (sp, bp) = legs["CE"], legs["PE"]
        credit = credit_of(legs)
        worst = sc["bid"] + sp["bid"] - bc["ask"] - bp["ask"]          # sell at bid, buy at ask
        wmax = max(bc["strike"] - sc["strike"], sp["strike"] - bp["strike"])
        qty = lot_size(exp)
        print(f"credit {credit:.2f} pts = {credit / width * 100:.1f}% of width; selling at bid and buying at ask "
              f"{worst:.2f} pts (slippage {credit - worst:.2f} pts)")
        print(f"target +{tp_frac * credit:.2f} pts ({tp_frac:.0%}), stop -{float(cfg.SL_FRACTION) * credit:.2f} pts, "
              f"max loss at expiry {wmax - credit:.2f} pts; lot size {qty} -> credit Rs {credit * qty:,.0f}, "
              f"max loss Rs {(wmax - credit) * qty:,.0f}")
        return rows

    wide, narrow = int(cfg.FWD_WIDE_WIDTH), int(cfg.HEDGE_WIDTH)
    legs_w, notes_w = build(wide, show=True)
    legs_n, notes_n = build(narrow, show=False)

    # 10-day move for the decision: closes before the snapshot day (NSE), unless given with --move
    if a.move is not None:
        move, move_src = a.move, "--move"
    else:
        n_ = int(cfg.TREND_LOOKBACK_DAYS)
        # during market hours: closes before today (the entry day); after the close the snapshot is a
        # preview for the next session, so that day's own close counts too
        before = ts.date() if ts.time() < dt.time(15, 30) else ts.date() + dt.timedelta(days=1)
        closes, move_src = get_closes(before, n_ + 1)
        move = (closes[-1][1] / closes[0][1] - 1) * 100 if len(closes) > n_ else None

    print("\n=== Forward-test decision ===")
    if move is None:
        print("10-day move not available - pass it with --move X.XX")
    else:
        print(f"10-day move {move:+.2f}% ({move_src})")
    width = None
    if legs_w is None:
        print(f"{wide}-pt condor cannot be priced: {'; '.join(notes_w)}")
        print("The credit test needs it - check the hedge strikes in the broker terminal and decide by hand.")
    elif move is not None:
        cw = credit_of(legs_w)
        width, why = fwd_decide(cfg, move, cw)
        print(f"{wide}-pt condor credit {cw:.2f} pts = {cw / wide * 100:.1f}% of width")
        print(f"DECISION: {'SKIP' if width is None else f'{width}-pt condor'} - {why}")
    lim = cfg.SKIP_IF_10D_MOVE_PCT
    if move is not None and lim:
        print(f"earlier rule (shadow log): {'SKIP' if abs(move) > float(lim) else f'{narrow}-pt condor'} "
              f"(|10-day move| limit {lim}%)")

    saved = []
    if legs_w is not None:
        chosen = width == wide
        saved += [(wide, r) for r in report(wide, legs_w, notes_w, tp_fraction(cfg, wide),
                                            f"{wide}-pt condor{' - CHOSEN' if chosen else ' (credit test)'}")]
    if legs_n is not None:
        chosen = width == narrow
        saved += [(narrow, r) for r in report(narrow, legs_n, notes_n, tp_fraction(cfg, narrow),
                                              f"{narrow}-pt condor{' - CHOSEN' if chosen else ' (shadow log / earlier rule)'}")]
    else:
        print(f"\n{narrow}-pt condor cannot be priced: {'; '.join(notes_n)}")
    print("\nThese are the strikes the rules point to, not an instruction to trade. NSE's website chain can lag "
          "a few minutes; confirm live prices in the broker terminal before paper-filling.")
    if a.save:
        os.makedirs(os.path.dirname(a.save) or ".", exist_ok=True)
        with open(a.save, "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["snapshot", "expiry", "nifty", "move_10d", "decision_width", "width", "leg", "strike", "delta",
                        "bid", "ask", "price", "last", "note"])
            for wd, (name, q) in saved:
                w.writerow([ts, exp, spot, "" if move is None else f"{move:.2f}", width or "SKIP", wd, name, q["strike"],
                            "" if not q["delta"] else f"{q['delta']:.4f}", q["bid"], q["ask"], f"{q['px']:.2f}",
                            q["last"], q["flag"]])
        print(f"saved to {a.save}")


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
    width = max(float(t["buy_ce"]) - float(t["sell_ce"]), float(t["sell_pe"]) - float(t["buy_pe"]))
    tpf = tp_fraction(cfg, width)                    # 60% for the wide condor, TP_FRACTION otherwise
    tp, sl = tpf * credit, -float(cfg.SL_FRACTION) * credit
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
    print(f"{width:.0f}-pt condor: target {tp:+.2f} ({tpf:.0%}), stop {sl:+.2f}, time exit date {ex}")
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
    x = s.add_parser("holidays")
    x.add_argument("--write", action="store_true", help="update NSE_HOLIDAYS in ic/config.py")
    x = s.add_parser("strikes")
    x.add_argument("--expiry", required=True)
    x.add_argument("--delta", type=float, default=TARGET_DELTA)
    x.add_argument("--move", type=float, help="10-day move in percent (default: worked out from NSE closes)")
    x.add_argument("--save", help="write the four legs with bid/ask to this CSV (e.g. journal/entry_quotes_N.csv)")
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
    {"rules": cmd_rules, "filter": cmd_filter, "plan": cmd_plan, "holidays": cmd_holidays, "strikes": cmd_strikes,
     "check": cmd_check, "export-ref": cmd_export_ref}[a.cmd](cfg, a)


if __name__ == "__main__":
    main()
