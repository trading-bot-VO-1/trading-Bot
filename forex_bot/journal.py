"""
Trade journal - reads YOUR closed trades from MT5 history automatically.

For each closed trade: pair, direction, lots, entry/exit, P&L, R-multiple
(if you used a stop-loss), and whether it matched an advisor signal.
"""
import os

import numpy as np
import pandas as pd

import config
import risk
from live import TF_MINUTES

ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY = 0, 1, 2, 3


def closed_trades(live, days=None):
    days = days or config.JOURNAL_DAYS
    now = live.server_time()
    deals = live.deals(now - pd.Timedelta(days=days), now + pd.Timedelta(days=1))
    if deals.empty:
        return pd.DataFrame()
    deals = deals[deals["type"].isin([0, 1])]          # buy/sell deals only
    for c in ("commission", "swap", "fee"):
        if c not in deals:
            deals[c] = 0.0
    opens = deals[deals.entry == ENTRY_IN]
    closes = deals[deals.entry.isin([ENTRY_OUT, ENTRY_OUT_BY])]

    rows = []
    for pid, g in closes.groupby("position_id"):
        o = opens[opens.position_id == pid]
        if o.empty:
            continue
        o = o.iloc[0]
        pnl = float((g.profit + g.commission + g.swap + g.fee).sum() + o.commission + o.fee)
        sym = o.base
        direction = "BUY" if o.type == 0 else "SELL"
        exit_price = float(np.average(g.price, weights=g.volume))
        sl = live.position_sl(int(pid))
        r = None
        if sl and sym in live.symbols:
            risk_money = risk.money_per_price(live.spec(sym), abs(o.price - sl), o.volume)
            r = round(pnl / risk_money, 2) if risk_money > 0 else None
        rows.append({
            "position": int(pid), "symbol": sym, "direction": direction, "lots": float(o.volume),
            "open_time": o.time, "close_time": g.time.max(), "entry": float(o.price),
            "exit": exit_price, "sl": sl, "pnl": round(pnl, 2), "r": r,
            "hours": round((g.time.max() - o.time).total_seconds() / 3600, 1),
        })
    trades = pd.DataFrame(rows)
    if trades.empty:
        return trades
    trades["followed_signal"] = _match_signals(trades)
    return trades.sort_values("close_time", ascending=False).reset_index(drop=True)


def _match_signals(trades):
    """A trade 'followed' a signal if a signal for the same pair+direction was logged
    within 2 candles before it opened."""
    if not os.path.exists(config.SIGNALS_LOG):
        return [False] * len(trades)
    log = pd.read_csv(config.SIGNALS_LOG, parse_dates=["signal_bar"])
    out = []
    for t in trades.itertuples():
        m = log[(log.symbol == t.symbol) & (log.direction == t.direction)]
        hit = False
        for s in m.itertuples():
            win = pd.Timedelta(minutes=3 * TF_MINUTES.get(s.timeframe, 60))
            if s.signal_bar <= t.open_time <= s.signal_bar + win:
                hit = True
                break
        out.append(hit)
    return out


def stats(trades):
    if trades is None or trades.empty:
        return {}
    wins, losses = trades.pnl[trades.pnl > 0], trades.pnl[trades.pnl < 0]
    r = trades.r.dropna()
    return {
        "trades": len(trades),
        "net_pnl": round(trades.pnl.sum(), 2),
        "win_rate": round((trades.pnl > 0).mean() * 100, 1),
        "profit_factor": round(wins.sum() / -losses.sum(), 2) if len(losses) else float("inf"),
        "avg_win": round(wins.mean(), 2) if len(wins) else 0.0,
        "avg_loss": round(losses.mean(), 2) if len(losses) else 0.0,
        "avg_r": round(r.mean(), 2) if len(r) else None,
        "no_stop_loss": int(trades.sl.isna().sum()),
        "followed_signals": int(trades.followed_signal.sum()),
    }


def breakdown(trades, by):
    if trades is None or trades.empty:
        return pd.DataFrame()
    g = trades.groupby(by)
    return pd.DataFrame({
        "trades": g.size(),
        "win_rate_%": g.pnl.apply(lambda p: round((p > 0).mean() * 100, 1)),
        "net_pnl": g.pnl.sum().round(2),
        "avg_r": g.r.mean().round(2),
    }).sort_values("net_pnl", ascending=False)
