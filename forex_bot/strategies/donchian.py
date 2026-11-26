"""
Strategy 4: Donchian channel breakout - classic "Turtle" trend-following (D1).

BUY  when the daily close breaks ABOVE the highest high of the previous 55 days.
SELL when the daily close breaks BELOW the lowest low of the previous 55 days.
Only the first close beyond the channel counts (fresh breakout).

Initial stop  = DONCHIAN_SL_ATR x ATR.
Exit          = 20-day channel: a long is closed when price hits the lowest low
                of the last 20 days (short: highest high). The stop follows that
                channel from day one, so winners run for weeks and losers are cut.
There is no fixed target: a few big trends pay for many small losses.
"""


def signals(df, cfg):
    n = cfg.DONCHIAN_ENTRY
    upper = df.high.rolling(n).max().shift(1)
    lower = df.low.rolling(n).min().shift(1)

    up = (df.close > upper) & (df.close.shift(1) <= upper.shift(1))
    dn = (df.close < lower) & (df.close.shift(1) >= lower.shift(1))

    sig = up.astype(int) - dn.astype(int)
    sl = cfg.DONCHIAN_SL_ATR * df.atr
    tp = cfg.DONCHIAN_TP_ATR * df.atr
    return sig, sl, tp, "channel"
