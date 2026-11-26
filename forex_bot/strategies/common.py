"""Helpers shared by strategies."""
import pandas as pd


def daily_trend(df, ema_period=50, slope_bars=3):
    """Daily trend for any intraday dataframe, using only COMPLETED days (no look-ahead).

    Returns (up, down) boolean Series aligned to df.index:
      up   = yesterday's daily close above daily EMA and the EMA rising
      down = mirror image
    """
    d = (df.set_index("time")[["open", "high", "low", "close"]]
         .resample("D").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
         .dropna())
    ema = d.close.ewm(span=ema_period, adjust=False).mean()
    up_d = ((d.close > ema) & (ema > ema.shift(slope_bars))).shift(1)
    dn_d = ((d.close < ema) & (ema < ema.shift(slope_bars))).shift(1)

    day = df.time.dt.normalize()
    up = day.map(up_d).astype("boolean").fillna(False).astype(bool)
    dn = day.map(dn_d).astype("boolean").fillna(False).astype(bool)
    up.index, dn.index = df.index, df.index
    return up, dn


def confirmed_swings(df, k=3):
    """Most recent CONFIRMED swing high / low at each bar.
    A swing high at bar i needs k lower highs on each side, so it is only
    known k bars later -> shifted by k (no look-ahead)."""
    w = 2 * k + 1
    piv_hi = df.high == df.high.rolling(w, center=True).max()
    piv_lo = df.low == df.low.rolling(w, center=True).min()
    swing_hi = df.high.where(piv_hi).shift(k).ffill()
    swing_lo = df.low.where(piv_lo).shift(k).ffill()
    return swing_hi, swing_lo
