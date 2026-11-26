"""
Runs every enabled strategy on a pair, applies the regime + volatility filter,
and merges them into ONE signal per candle (priority = order in config.STRATEGIES).

Output columns used by the backtest (and later the live bot):
  signal    1 buy / -1 sell / 0 none   (acted on at the NEXT candle's open)
  sl_dist   stop distance in price
  tp_dist   target distance in price
  strategy  name of the strategy that fired
  trail     whether that strategy trails its stop
  regime    trend / range / neutral
"""
import numpy as np

from indicators import adx, atr, bollinger, ema, rsi
from strategies import breakout, meanrev, trend

REGISTRY = {"trend": trend, "breakout": breakout, "meanrev": meanrev}


def add_indicators(df, cfg):
    df = df.copy()
    df["ema_fast"] = ema(df.close, cfg.EMA_FAST)
    df["ema_slow"] = ema(df.close, cfg.EMA_SLOW)
    df["atr"] = atr(df, cfg.ATR_PERIOD)
    df["adx"] = adx(df, cfg.ADX_PERIOD)
    df["rsi"] = rsi(df.close, cfg.RSI_PERIOD)
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = bollinger(df.close, cfg.BB_PERIOD, cfg.BB_STD)

    df["regime"] = np.select([df.adx >= cfg.ADX_TREND, df.adx < cfg.ADX_RANGE],
                             ["trend", "range"], "neutral")
    normal_atr = df.atr.rolling(cfg.VOL_LOOKBACK).median()
    ratio = df.atr / normal_atr
    df["vol_ok"] = (ratio >= cfg.VOL_MIN_RATIO) & (ratio <= cfg.VOL_MAX_RATIO)
    return df


def prepare(df, cfg):
    df = add_indicators(df, cfg)
    df["signal"] = 0
    df["sl_dist"] = np.nan
    df["tp_dist"] = np.nan
    df["strategy"] = ""
    df["trail"] = False

    # lowest priority first, so higher-priority strategies overwrite it
    for name in reversed(cfg.STRATEGIES):
        sig, sl, tp, trail = REGISTRY[name].signals(df, cfg)
        ok = (sig != 0) & sl.notna() & (sl > 0)
        if cfg.USE_REGIME_FILTER:
            ok &= df.vol_ok & df.regime.isin(cfg.REGIME_ALLOWED[name])
        df.loc[ok, "signal"] = sig[ok]
        df.loc[ok, "sl_dist"] = sl[ok]
        df.loc[ok, "tp_dist"] = tp[ok]
        df.loc[ok, "strategy"] = name
        df.loc[ok, "trail"] = trail

    warmup = max(cfg.EMA_SLOW, cfg.VOL_LOOKBACK) + 3 * cfg.ADX_PERIOD
    df.loc[df.index[:warmup], "signal"] = 0
    return df
