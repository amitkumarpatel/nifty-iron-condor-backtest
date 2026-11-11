"""Black-Scholes price, delta and implied volatility (European, NSE index options) - shared by every strategy."""
import math

from shared import config as C


def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, vol, opt):
    """Black-Scholes (price, delta) of a European option; T in years."""
    r, q = C.RISK_FREE_RATE, C.DIV_YIELD
    d1 = (math.log(S / K) + (r - q + vol * vol / 2) * T) / (vol * math.sqrt(T))
    d2 = d1 - vol * math.sqrt(T)
    if opt == "CE":
        return (S * math.exp(-q * T) * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2), math.exp(-q * T) * _ncdf(d1))
    return (K * math.exp(-r * T) * _ncdf(-d2) - S * math.exp(-q * T) * _ncdf(-d1), -math.exp(-q * T) * _ncdf(-d1))


def implied_vol(px, S, K, T, opt):
    lo, hi = 0.01, 3.0
    if not bs(S, K, T, lo, opt)[0] < px < bs(S, K, T, hi, opt)[0]:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bs(S, K, T, mid, opt)[0] < px else (lo, mid)
    return (lo + hi) / 2
