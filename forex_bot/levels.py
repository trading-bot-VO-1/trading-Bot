"""
Support / resistance levels from confirmed swing points, clustered into zones.
"""
import numpy as np


def swing_points(df, k=3):
    """Confirmed swing highs/lows (k candles each side). Returns arrays of prices."""
    w = 2 * k + 1
    hi = df.high[df.high == df.high.rolling(w, center=True).max()]
    lo = df.low[df.low == df.low.rolling(w, center=True).min()]
    return hi.dropna().values, lo.dropna().values


def zones(df, lookback=150, k=3, tol_atr=0.5):
    """Cluster recent swing points into levels. Returns list of (price, touches)."""
    d = df.tail(lookback)
    atr = (d.high - d.low).mean()
    hi, lo = swing_points(d, k)
    pts = np.sort(np.concatenate([hi, lo]))
    levels = []
    for p in pts:
        if levels and abs(p - levels[-1][0]) <= tol_atr * atr:
            price, n = levels[-1]
            levels[-1] = ((price * n + p) / (n + 1), n + 1)
        else:
            levels.append((p, 1))
    return levels


def nearest(df, price, atr, **kw):
    """Nearest support below and resistance above price: dicts with price, touches, distance in ATR."""
    lv = zones(df, **kw)
    below = [l for l in lv if l[0] < price]
    above = [l for l in lv if l[0] > price]
    sup = max(below, key=lambda l: l[0]) if below else None
    res = min(above, key=lambda l: l[0]) if above else None
    fmt = lambda l: None if l is None else {
        "price": l[0], "touches": l[1], "dist_atr": round(abs(price - l[0]) / atr, 2) if atr else None}
    return fmt(sup), fmt(res)
