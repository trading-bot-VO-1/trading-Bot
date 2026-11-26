"""
Strategy 3: Mean reversion (H1) - for ranging markets only.

BUY on a closed candle when:
  - ADX < ADX_RANGE                    (no trend)
  - close is below the lower Bollinger Band
  - RSI < RSI_LOW                      (oversold)
SELL is the mirror image (above upper band, RSI > RSI_HIGH).

Stop = MR_SL_ATR x ATR, target = MR_RR x stop. No trailing (takes its target).
"""


def signals(df, cfg):
    ranging = df.adx < cfg.ADX_RANGE
    buy = ranging & (df.close < df.bb_lower) & (df.rsi < cfg.RSI_LOW)
    sell = ranging & (df.close > df.bb_upper) & (df.rsi > cfg.RSI_HIGH)

    sig = buy.astype(int) - sell.astype(int)
    sl = cfg.MR_SL_ATR * df.atr
    return sig, sl, sl * cfg.MR_RR, cfg.MR_TRAIL
