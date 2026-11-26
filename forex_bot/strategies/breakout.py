"""
Strategy 2: Asian-range breakout at the London open (H1, server-time hours).

  - Asian range = high/low of candles from ASIA_START_HOUR to ASIA_END_HOUR-1.
  - Between ASIA_END_HOUR and BREAKOUT_END_HOUR, the first candle that CLOSES
    beyond the range (+ buffer) gives the signal: above = BUY, below = SELL.
  - Only one breakout per pair per day.
  - Skip days where the Asian range is abnormally wide.

Stop = range height, clamped between BREAKOUT_SL_MIN_ATR and BREAKOUT_SL_MAX_ATR x ATR.
Target = BREAKOUT_RR x stop. Trails after breakeven.
"""
import numpy as np


def signals(df, cfg):
    hour = df.time.dt.hour
    day = df.time.dt.normalize()

    in_asia = (hour >= cfg.ASIA_START_HOUR) & (hour < cfg.ASIA_END_HOUR)
    asia_hi = df.high.where(in_asia).groupby(day).transform("max")
    asia_lo = df.low.where(in_asia).groupby(day).transform("min")
    height = asia_hi - asia_lo

    window = (hour >= cfg.ASIA_END_HOUR) & (hour < cfg.BREAKOUT_END_HOUR)
    buf = cfg.BREAKOUT_BUFFER_ATR * df.atr
    range_ok = height <= cfg.BREAKOUT_MAX_RANGE_ATR * df.atr

    up = window & range_ok & (df.close > asia_hi + buf)
    dn = window & range_ok & (df.close < asia_lo - buf)
    raw = up.astype(int) - dn.astype(int)

    # keep only the first breakout of each day
    first = (raw != 0) & ((raw != 0).astype(int).groupby(day).cumsum() == 1)
    sig = raw.where(first, 0).astype(int)

    sl = np.clip(height, cfg.BREAKOUT_SL_MIN_ATR * df.atr, cfg.BREAKOUT_SL_MAX_ATR * df.atr)
    return sig, sl, sl * cfg.BREAKOUT_RR, cfg.BREAKOUT_TRAIL
