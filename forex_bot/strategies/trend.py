"""
Strategy 1: Trend-following pullback (H1).

LONG on a closed candle when:
  - EMA50 > EMA200 and close > EMA200        (uptrend)
  - ADX >= ADX_TREND                         (trend is strong)
  - candle's low touched EMA50, it closed above EMA50, bullish candle  (pullback bounce)
SHORT is the mirror image.

Stop = TREND_SL_ATR x ATR, target = TREND_RR x stop. Trails after breakeven.
Expects columns from strategies.combine.add_indicators().
"""


def signals(df, cfg):
    uptrend = (df.ema_fast > df.ema_slow) & (df.close > df.ema_slow)
    downtrend = (df.ema_fast < df.ema_slow) & (df.close < df.ema_slow)
    strong = df.adx >= cfg.ADX_TREND

    bounce_up = (df.low <= df.ema_fast) & (df.close > df.ema_fast) & (df.close > df.open)
    bounce_dn = (df.high >= df.ema_fast) & (df.close < df.ema_fast) & (df.close < df.open)

    sig = (uptrend & strong & bounce_up).astype(int) - (downtrend & strong & bounce_dn).astype(int)
    sl = cfg.TREND_SL_ATR * df.atr
    return sig, sl, sl * cfg.TREND_RR, cfg.TREND_TRAIL
