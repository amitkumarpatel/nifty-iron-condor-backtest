"""
Fallback strikes - when a leg has no usable price at entry, use the nearest strikes that have one,
the way the user handles missing strikes in StockMock:

1. a side (CE or PE) is broken if its sold leg or hedge has no usable entry price (no trade before
   ENTRY_TIME, or the first trade came more than MAX_AFTER_MIN_AT_ENTRY minutes later), or the hedge
   is priced at or above the sold leg;
2. shift that side's whole spread (sold + hedge, same width) by FALLBACK_SHIFTS points - negative =
   closer to the money - and take the first pair with usable, consistent prices;
3. else keep the sold strike and widen the hedge to FALLBACK_HEDGE_WIDTHS;
4. else leave the side as it is (the trade is then not run).
"""
import pandas as pd

from ic import config as C
from ic.common import contract_key


def usable_price(key, day):
    from ic.engine import price_at
    px, q, m = price_at(key, day, C.ENTRY_TIME)
    if px is None or (q == "AFTER" and -m > C.MAX_AFTER_MIN_AT_ENTRY):
        return None
    return px


def candidates(sold, width, opt):
    """(sold strike, hedge strike, description) to try, in order."""
    out_ = 1 if opt == "CE" else -1                    # +1 = further out of the money
    out = []
    for s in C.FALLBACK_SHIFTS:
        k = sold + out_ * s
        out.append((k, k + out_ * width, f"spread {abs(s)} pts {'closer' if s < 0 else 'further out'}"))
    for w in C.FALLBACK_HEDGE_WIDTHS:
        out.append((sold, sold + out_ * w, f"hedge widened to {w} pts"))
    return out


def choose(t, tlegs):
    """Return (legs, note, keys_checked). `legs` is `tlegs` with any broken side moved to fallback
    strikes (moved legs lose their StockMock prices); `note` is '' when nothing changed."""
    day, exp = t.entry_date.date(), t.expiry.strftime("%Y-%m-%d")
    legs, notes, checked = tlegs.copy(), [], []
    for opt in ("CE", "PE"):
        s = legs[(legs.side == "SELL") & (legs.opt_type == opt)]
        b = legs[(legs.side == "BUY") & (legs.opt_type == opt)]
        if s.empty or b.empty:
            continue
        s, b = s.iloc[0], b.iloc[0]
        ps, pb = usable_price(s.key, day), usable_price(b.key, day)
        if ps is None and C.USE_REFERENCE_ENTRY_IF_MISSING and pd.notna(s.entry_px):
            ps = float(s.entry_px)                     # StockMock price for StockMock's own strike
        if ps is not None and pb is not None and pb < ps:
            continue
        width = int(abs(b.strike - s.strike))
        for ks, kb, why in candidates(int(s.strike), width, opt):
            k1, k2 = contract_key(exp, ks, opt), contract_key(exp, kb, opt)
            checked += [k1, k2]
            p1, p2 = usable_price(k1, day), usable_price(k2, day)
            if p1 is not None and p2 is not None and p2 < p1:
                legs.loc[s.name, ["strike", "key", "entry_px", "exit_px"]] = [ks, k1, float("nan"), float("nan")]
                legs.loc[b.name, ["strike", "key", "entry_px", "exit_px"]] = [kb, k2, float("nan"), float("nan")]
                notes.append(f"{opt} {int(s.strike)}/{int(b.strike)} -> {ks}/{kb} ({why})")
                break
        else:
            notes.append(f"{opt} {int(s.strike)}/{int(b.strike)}: no usable fallback strike")
    return legs, "; ".join(notes), checked
