"""Fake BreezeConnect for offline tests. Each contract's price moves linearly (per trading day)
from its StockMock entry price to its StockMock exit price. Strikes 16950 and 13500 return no data (13500PE exercises the fallback strikes) and
strike 17750 has a 11:10-11:20 gap, to exercise the missing-data and fallback paths.
Other strikes get the nearest reference strike's prices scaled by exp(-OTM distance/250); NIFTY spot
1-minute candles are the midpoint of that day's sold strikes.
The numbers are NOT market data - only the pipeline is being tested."""
import math
from datetime import date, datetime, timedelta

import pandas as pd

from ic import config as C

_legs = pd.read_csv(C.LEGS_CSV)
REF = {(r.expiry, int(r.strike), r.opt_type): (date.fromisoformat(r.entry_dt[:10]), r.entry_px,
                                               date.fromisoformat(r.exit_dt[:10]), r.exit_px)
       for r in _legs.itertuples()}
HOL = {date(2026, 9, 14), date(2022, 8, 15), date(2025, 4, 14)}
NO_DATA = {16950, 13500}   # no trades at all: 16950PE (has a StockMock price), 13500PE (300-pt hedge of trade 1)


def _tdays(a, b):
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d not in HOL:
            out.append(d)
        d += timedelta(days=1)
    return out


class BreezeConnect:
    def __init__(self, api_key):
        pass

    def generate_session(self, api_secret, session_token):
        pass

    def get_historical_data_v2(self, **p):
        f = datetime.strptime(p["from_date"][:16], "%Y-%m-%dT%H:%M")
        t = datetime.strptime(p["to_date"][:16], "%Y-%m-%dT%H:%M")
        if p["interval"] == "1day":
            return {"Success": [{"datetime": f"{d} 00:00:00", "close": 1} for d in _tdays(f.date(), t.date())],
                    "Error": None}
        if p.get("product_type") == "cash":   # NIFTY 1-minute spot: midpoint of that day's sold strikes
            mids = [(k0 + k1) / 2 for (e, k0, o), (d0, *_ ) in REF.items() if o == "CE" and d0 == f.date()
                    for (e2, k1, o2), (d1, *_ ) in REF.items() if o2 == "PE" and d1 == f.date() and e2 == e]
            spot = round(sum(mids) / len(mids), 2) if mids else 20000.0
            out, m = [], f
            while m <= t and m.hour * 60 + m.minute <= 15 * 60 + 29:
                out.append({"datetime": m.strftime("%Y-%m-%d %H:%M:%S"), "open": spot, "high": spot, "low": spot, "close": spot})
                m += timedelta(minutes=1)
            return {"Success": out, "Error": None}
        k = (p["expiry_date"][:10], int(p["strike_price"]), "CE" if p["right"] == "call" else "PE")
        if k[1] in NO_DATA:
            return {"Success": None, "Error": "No Data Found"}
        scale = 1.0
        if k not in REF:   # other strike: nearest reference strike's prices, cheaper further out of the money
            same = [r for r in REF if r[0] == k[0] and r[2] == k[2] and r[1] not in NO_DATA]
            if same:
                near = min(same, key=lambda r: abs(r[1] - k[1]))
                otm = (k[1] - near[1]) if k[2] == "CE" else (near[1] - k[1])
                k, scale = near, math.exp(-otm / 250)
        if k not in REF or k[1] in NO_DATA:
            return {"Success": None, "Error": "No Data Found"}
        e0, p0, e1, p1 = REF[k]
        p0, p1 = p0 * scale, p1 * scale
        n = max(1, len(_tdays(e0, e1)) - 1)
        out = []
        for d in _tdays(f.date(), t.date()):
            i = len(_tdays(e0, d)) - 1
            px = round(p0 + (p1 - p0) * min(i, n) / n, 2)
            m = datetime(d.year, d.month, d.day, 9, 15)
            while m <= min(datetime(d.year, d.month, d.day, 15, 29), t):
                if m >= f and not (k[1] == 17750 and m.hour == 11 and 10 <= m.minute <= 20):
                    out.append({"datetime": m.strftime("%Y-%m-%d %H:%M:%S"), "open": px, "high": px,
                                "low": px, "close": px, "volume": 1, "open_interest": 1})
                m += timedelta(minutes=1)
        return {"Success": out, "Error": None}
