"""
Strategy 5: Multi-timeframe confluence (base timeframe H4).

BUY when ALL three line up:
  1. D1 trend up      - yesterday's daily close above the daily EMA50, EMA50 rising
  2. H4 pullback      - RSI(14) dipped below 40 within the last 3 H4 candles
  3. H4 trigger       - H4 candle closes back above EMA20 (momentum resumes)
SELL is the mirror image (RSI above 60, close back below EMA20, D1 downtrend).

Stop   = beyond the lowest low / highest high of the last 10 H4 candles + 0.2 ATR,
         kept between 1 and 3 ATR.
Target = MTF_RR x stop. Trails after breakeven.
"""
import numpy as np
import pandas as pd

from indicators import ema
from strategies.common import daily_trend


def signals(df, cfg):
    up_d, dn_d = daily_trend(df, cfg.MTF_D1_EMA)
    ema_t = ema(df.close, cfg.MTF_EMA_TRIGGER)

    pull_up = df.rsi.rolling(3).min() < cfg.MTF_RSI_PULLBACK
    pull_dn = df.rsi.rolling(3).max() > 100 - cfg.MTF_RSI_PULLBACK
    trig_up = (df.close > ema_t) & (df.close.shift(1) <= ema_t.shift(1))
    trig_dn = (df.close < ema_t) & (df.close.shift(1) >= ema_t.shift(1))

    sig = (up_d & pull_up & trig_up).astype(int) - (dn_d & pull_dn & trig_dn).astype(int)

    lb = cfg.MTF_SWING_LOOKBACK
    sl_long = df.close - df.low.rolling(lb).min() + 0.2 * df.atr
    sl_short = df.high.rolling(lb).max() - df.close + 0.2 * df.atr
    sl = pd.Series(np.where(sig > 0, sl_long, sl_short), index=df.index)
    sl = sl.clip(lower=cfg.MTF_SL_MIN_ATR * df.atr, upper=cfg.MTF_SL_MAX_ATR * df.atr)
    return sig, sl, sl * cfg.MTF_RR, cfg.MTF_TRAIL
