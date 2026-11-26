"""
Risk manager: lot sizing, daily-loss lock, open-trade and currency exposure checks.
"""
import math

import pandas as pd

import config


def money_per_price(spec, price_diff, lots=1.0):
    return price_diff / spec["tick_size"] * spec["tick_value"] * lots


def lot_size(balance, risk_pct, sl_dist, spec):
    """Lots so that hitting the stop loses `risk_pct` of balance. Returns (lots, risk_money)."""
    if not sl_dist or sl_dist <= 0:
        return 0.0, 0.0
    per_lot = money_per_price(spec, sl_dist)
    if per_lot <= 0:
        return 0.0, 0.0
    step = spec["volume_step"]
    lots = math.floor(balance * risk_pct / per_lot / step + 1e-9) * step
    lots = min(lots, spec["volume_max"])
    if lots < spec["volume_min"]:
        return 0.0, 0.0
    lots = round(lots, 2)
    return lots, round(per_lot * lots, 2)


def pips(spec, price_diff):
    """Price distance in pips (1 pip = 10 points on 5/3-digit quotes)."""
    pip = spec["point"] * (10 if spec["digits"] in (3, 5) else 1)
    return price_diff / pip


def daily_status(live):
    """Today's P&L vs the start of the day, and whether the daily-loss lock is on."""
    acct = live.account()
    now = live.server_time()
    start = now.normalize()
    deals = live.deals(start, now + pd.Timedelta(days=1))
    realized = 0.0
    if not deals.empty:
        trades = deals[deals["type"].isin([0, 1])]
        realized = float((trades["profit"] + trades["commission"] + trades["swap"]
                          + trades.get("fee", 0)).sum())
    balance, equity = acct.get("balance", 0.0), acct.get("equity", 0.0)
    day_start = balance - realized
    pnl = equity - day_start
    pct = pnl / day_start if day_start else 0.0
    limit_money = day_start * config.DAILY_LOSS_LIMIT
    return {
        "day_start_balance": round(day_start, 2),
        "pnl_today": round(pnl, 2),
        "pnl_today_pct": round(pct * 100, 2),
        "loss_room": round(limit_money + pnl, 2),     # money left before the lock
        "locked": pct <= -config.DAILY_LOSS_LIMIT,
    }


def exposure(positions):
    """Net open direction per currency: long EURUSD = EUR +1, USD -1."""
    exp = {}
    for p in positions:
        b, q, d = p["base"][:3], p["base"][3:6], p["direction"]
        exp[b] = exp.get(b, 0) + d
        exp[q] = exp.get(q, 0) - d
    return exp


def currency_warnings(positions, symbol, direction):
    exp = exposure(positions)
    b, q = symbol[:3], symbol[3:6]
    after = {b: exp.get(b, 0) + direction, q: exp.get(q, 0) - direction}
    return [f"Adds to {abs(v)} same-direction trades on {c}"
            for c, v in after.items() if abs(v) > config.MAX_SAME_CURRENCY]


def trade_checks(live, positions, day, symbol, direction):
    """All reasons NOT to take a new trade right now (empty list = clear)."""
    warns = []
    if day["locked"]:
        warns.append(f"Daily loss limit hit ({day['pnl_today_pct']}% today) - stop trading for today")
    if len(positions) >= config.MAX_OPEN_TRADES:
        warns.append(f"You already have {len(positions)} open trades (max {config.MAX_OPEN_TRADES})")
    if any(p["base"] == symbol for p in positions):
        warns.append(f"You already have a position on {symbol}")
    warns += currency_warnings(positions, symbol, direction)
    return warns
