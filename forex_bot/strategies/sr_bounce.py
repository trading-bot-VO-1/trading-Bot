"""
Strategy 6: Support / resistance rejection with the daily trend (base timeframe H4).

BUY when:
  1. D1 trend up (same filter as mtf)
  2. price dips into the zone of the latest confirmed swing LOW (support)
     (low within SR_ZONE_ATR x ATR of it) but CLOSES above it
  3. the candle is a bullish rejection (pin bar): lower wick >= 50% of the range,
     close in the upper part of the candle
SELL is the mirror image at the latest swing HIGH (resistance) in a D1 downtrend.

Stop   = SR_SL_BUFFER_ATR x ATR beyond the level, kept between 0.5 and 3 ATR.
Target = SR_RR x stop. Breakeven at +1R, no trailing (default).
"""
import numpy as np
import pandas as pd

from strategies.common import confirmed_swings, daily_trend


def signals(df, cfg):
    up_d, dn_d = daily_trend(df, cfg.SR_D1_EMA)
    res, sup = confirmed_swings(df, cfg.SR_PIVOT)
    zone = cfg.SR_ZONE_ATR * df.atr
    buf = cfg.SR_SL_BUFFER_ATR * df.atr

    rng = (df.high - df.low).replace(0, np.nan)
    lower_wick = np.minimum(df.open, df.close) - df.low
    upper_wick = df.high - np.maximum(df.open, df.close)
    bull_pin = (lower_wick >= 0.5 * rng) & (df.close >= df.low + 0.6 * rng)
    bear_pin = (upper_wick >= 0.5 * rng) & (df.close <= df.high - 0.6 * rng)

    buy = up_d & (df.low <= sup + zone) & (df.close > sup) & bull_pin
    sell = dn_d & (df.high >= res - zone) & (df.close < res) & bear_pin
    sig = buy.astype(int) - sell.astype(int)

    sl_long = df.close - (sup - buf)
    sl_short = (res + buf) - df.close
    sl = pd.Series(np.where(sig > 0, sl_long, sl_short), index=df.index)
    sl = sl.clip(lower=0.5 * df.atr, upper=3.0 * df.atr)
    return sig, sl, sl * cfg.SR_RR, cfg.SR_TRAIL
