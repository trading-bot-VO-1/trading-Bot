"""
Signal engine - tells you WHAT to trade, WHERE and HOW BIG. Never places trades.

Only strategies APPROVED by the strategy lab (python lab.py) give "TAKE" signals.
Unproven strategies can be shown as "STUDY ONLY" if you switch that on.

Each signal: pair, BUY/SELL, entry, stop-loss, take-profit, lot size for your
balance, money at risk, reason, how to manage it, the setup's backtest record,
and any warnings (news, daily-loss lock, too many trades, currency overlap).
"""
import json
import os
import types

import numpy as np
import pandas as pd

import config
import news
import risk
from live import TF_MINUTES
from strategies import combine

MANAGE = {
    "atr": "At +1R move stop to entry (breakeven), then trail it {trail} x ATR behind price.",
    "none": "At +1R move stop to entry (breakeven). Leave the target in place.",
    "channel": ("No fixed target. Every day move the stop to the {exit}-day "
                "{side} - exit when price hits it. Let winners run for weeks."),
}


def cfg_for(strategies):
    c = types.SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.isupper()})
    c.STRATEGIES = list(strategies)
    return c


def load_lab():
    if not os.path.exists(config.LAB_RESULTS):
        return {}
    with open(config.LAB_RESULTS) as f:
        return json.load(f)


def _reason(strat, r, d):
    side = "up" if d > 0 else "down"
    if strat == "trend":
        return (f"H1 {side}trend (EMA50 {'above' if d > 0 else 'below'} EMA200, ADX {r.adx:.0f}); "
                f"price pulled back to EMA50 and bounced.")
    if strat == "breakout":
        return f"H1 candle closed {'above' if d > 0 else 'below'} the Asian-session range at the London open."
    if strat == "meanrev":
        return (f"Ranging market (ADX {r.adx:.0f}); price closed {'below the lower' if d > 0 else 'above the upper'} "
                f"Bollinger Band with RSI {r.rsi:.0f} - expecting a move back to the middle.")
    if strat == "donchian":
        return f"Daily close broke the {config.DONCHIAN_ENTRY}-day {'high' if d > 0 else 'low'} - new {side}trend."
    if strat == "mtf":
        return (f"D1 {side}trend + H4 pullback (RSI {r.rsi:.0f}) + H4 closed back "
                f"{'above' if d > 0 else 'below'} EMA{config.MTF_EMA_TRIGGER}: trend resuming.")
    if strat == "sr_bounce":
        return (f"D1 {side}trend; H4 rejection candle at {'support' if d > 0 else 'resistance'} "
                f"(long {'lower' if d > 0 else 'upper'} wick).")
    return strat


def _signal_for(live, strat, sym, row, lab, acct, positions, day, events, now):
    d = int(row.signal)
    spec, tick = live.spec(sym), live.tick(sym)
    if tick is None:
        return None
    digits = spec["digits"]
    entry = tick["ask"] if d > 0 else tick["bid"]
    sl_dist, tp_dist = float(row.sl_dist), float(row.tp_dist)
    sl = entry - d * sl_dist
    tp = None if row.trail == "channel" else entry + d * tp_dist
    risk_pct = getattr(config, "ADVISOR_RISK", config.RISK_PER_TRADE)
    lots, risk_money = risk.lot_size(acct.get("balance", 0.0), risk_pct, sl_dist, spec)

    approved = bool(lab.get(strat, {}).get("approved"))
    warnings = risk.trade_checks(live, positions, day, sym, d)
    if news.block_mask(sym, np.array([np.datetime64(now)]), events)[0]:
        warnings.append("High-impact news for this pair within the next hour - wait")
    if lots <= 0:
        warnings.append("Account too small for this stop distance at your risk % (below minimum lot)")

    tf = config.STRATEGY_TF[strat]
    bar_close = row.time + pd.Timedelta(minutes=TF_MINUTES[tf])
    status = ("TAKE" if not warnings else "SKIP") if approved else "STUDY ONLY"
    return {
        "key": f"{strat}|{sym}|{row.time:%Y-%m-%d %H:%M}",
        "status": status, "approved": approved,
        "symbol": sym, "direction": "BUY" if d > 0 else "SELL",
        "strategy": strat, "timeframe": tf,
        "signal_bar": row.time, "valid_until": bar_close + pd.Timedelta(minutes=TF_MINUTES[tf]),
        "entry": round(entry, digits), "sl": round(sl, digits),
        "tp": round(tp, digits) if tp is not None else None,
        "sl_pips": round(risk.pips(spec, sl_dist), 1),
        "tp_pips": round(risk.pips(spec, tp_dist), 1) if tp is not None else None,
        "rr": round(tp_dist / sl_dist, 2) if tp is not None else None,
        "lots": lots, "risk_money": risk_money, "risk_pct": risk_pct * 100,
        "reason": _reason(strat, row, d),
        "manage": MANAGE[row.trail].format(trail=config.TRAIL_ATR_MULT, exit=config.DONCHIAN_EXIT,
                                           side="low" if d > 0 else "high"),
        "stats": lab.get(strat, {}).get("pairs", {}).get(sym),
        "strategy_stats": lab.get(strat, {}).get("out_of_sample"),
        "warnings": warnings,
    }


def find_signals(live, include_unproven=False):
    """Check every pair for a signal on the LAST CLOSED candle of each strategy's timeframe.
    Returns (signals, daily_status)."""
    lab = load_lab()
    names = [s for s in config.LAB_STRATEGIES
             if lab.get(s, {}).get("approved") or include_unproven]
    acct = live.account()
    positions = live.positions()
    day = risk.daily_status(live)
    events = news.load_events()
    now = live.server_time()

    out = []
    for strat in names:
        tf, cfg = config.STRATEGY_TF[strat], cfg_for([strat])
        for sym in live.symbols:
            df = live.bars(sym, tf)
            if df is None or len(df) < 300:
                continue
            p = combine.prepare(df, cfg)
            row = p.iloc[-1]
            if row.signal == 0:
                continue
            # signal is only fresh until the next candle closes
            if now > row.time + pd.Timedelta(minutes=2 * TF_MINUTES[tf]):
                continue
            s = _signal_for(live, strat, sym, row, lab, acct, positions, day, events, now)
            if s:
                out.append(s)
    order = {"TAKE": 0, "SKIP": 1, "STUDY ONLY": 2}
    out.sort(key=lambda s: (order[s["status"]], s["symbol"]))
    return out, day


LOG_COLS = ["key", "logged_at", "status", "symbol", "direction", "strategy", "timeframe",
            "signal_bar", "entry", "sl", "tp", "lots", "approved"]


def record_new(signals):
    """Append signals not seen before to the signals log. Returns the new ones."""
    path = config.SIGNALS_LOG
    seen = set()
    if os.path.exists(path):
        seen = set(pd.read_csv(path, usecols=["key"])["key"])
    new = [s for s in signals if s["key"] not in seen]
    if new:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = pd.DataFrame([{**{c: s.get(c) for c in LOG_COLS}, "logged_at": now} for s in new])
        rows.to_csv(path, mode="a", header=not os.path.exists(path), index=False)
    return new


def format_signal(s):
    lines = [f"{s['status']}: {s['direction']} {s['symbol']}  ({s['strategy']}, {s['timeframe']})",
             f"Entry {s['entry']} | SL {s['sl']} ({s['sl_pips']} pips) | "
             + (f"TP {s['tp']} ({s['tp_pips']} pips, 1:{s['rr']})" if s['tp'] else "TP: none (channel exit)"),
             f"Lots {s['lots']} | Risk ${s['risk_money']} ({s['risk_pct']:.1f}%)",
             f"Why: {s['reason']}",
             f"Manage: {s['manage']}",
             f"Valid until {s['valid_until']:%Y-%m-%d %H:%M} (server time)"]
    if s["stats"]:
        st = s["stats"]
        lines.append(f"Backtest on {s['symbol']}: {st['trades']} trades, win {st['win_rate']}%, PF {st['profit_factor']}")
    for w in s["warnings"]:
        lines.append(f"! {w}")
    return "\n".join(lines)
