"""
Indicators written in plain pandas (no pandas-ta dependency, which breaks on numpy 2).
Formulas match MT5 / TradingView (Wilder smoothing for ATR, ADX, RSI).
"""
import numpy as np
import pandas as pd


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def _wilder(series, period):
    return series.ewm(alpha=1.0 / period, adjust=False).mean()


def true_range(df):
    prev_close = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(df, period=14):
    return _wilder(true_range(df), period)


def adx(df, period=14):
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    atr_ = _wilder(true_range(df), period)
    plus_di = 100 * _wilder(plus_dm, period) / atr_
    minus_di = 100 * _wilder(minus_dm, period) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return _wilder(dx.fillna(0), period)


def rsi(series, period=14):
    delta = series.diff()
    gain = _wilder(delta.clip(lower=0), period)
    loss = _wilder(-delta.clip(upper=0), period)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def bollinger(series, period=20, std=2.0):
    mid = series.rolling(period).mean()
    sd = series.rolling(period).std(ddof=0)
    return mid, mid + std * sd, mid - std * sd
