"""
Market scanner: what is every pair doing right now, in plain English.

For each pair: D1 and H4 trend, market state (trend / range / volatile),
nearest support & resistance, upcoming news, and a watch score
(higher = cleaner conditions to look for trades).
"""
import pandas as pd

import config
import levels
import news
from strategies import combine

SESSIONS_UTC = {"Sydney": (21, 6), "Tokyo": (0, 9), "London": (7, 16), "New York": (12, 21)}


def active_sessions(now_server):
    h = news.server_to_utc(now_server).hour
    out = []
    for name, (a, b) in SESSIONS_UTC.items():
        if (a <= h < b) if a < b else (h >= a or h < b):
            out.append(name)
    return out


def _direction(row):
    if row.ema_fast > row.ema_slow and row.close > row.ema_slow:
        return "Up"
    if row.ema_fast < row.ema_slow and row.close < row.ema_slow:
        return "Down"
    return "Sideways"


def _vol_label(row):
    normal = row.get("atr_norm")
    if not normal or pd.isna(normal):
        return "normal", 1.0
    r = row.atr / normal
    if r < config.VOL_MIN_RATIO:
        return "quiet", r
    if r > config.VOL_MAX_RATIO:
        return "volatile", r
    return "normal", r


def analyse_pair(live, sym, events, now):
    d1 = live.bars(sym, "D1", 400)
    h4 = live.bars(sym, "H4", 600)
    if d1 is None or h4 is None or len(d1) < 220 or len(h4) < 220:
        return None
    D = combine.add_indicators(d1, config)
    H = combine.add_indicators(h4, config)
    H["atr_norm"] = H.atr.rolling(config.VOL_LOOKBACK).median()
    dl, hl = D.iloc[-1], H.iloc[-1]

    d_dir, h_dir = _direction(dl), _direction(hl)
    vol, vol_ratio = _vol_label(hl)
    price = hl.close
    sup, res = levels.nearest(d1, price, dl.atr)
    ev = news.upcoming(events, [sym[:3], sym[3:6]], now, 24)
    next_news = None if ev is None or ev.empty else \
        f"{ev.iloc[0].currency} {ev.iloc[0].title} @ {ev.iloc[0].server_time:%a %H:%M}"

    # ---- state + plain-English advice ----
    near_sup = sup and sup["dist_atr"] is not None and sup["dist_atr"] <= 0.5
    near_res = res and res["dist_atr"] is not None and res["dist_atr"] <= 0.5
    digits = live.spec(sym)["digits"]
    sp = f"{sup['price']:.{digits}f}" if sup else "-"
    rp = f"{res['price']:.{digits}f}" if res else "-"

    score = 0
    if vol == "volatile":
        state, advice = "Volatile", "Moves are abnormally large - stay out until it calms down."
        score -= 3
    elif d_dir == "Up" and h_dir == "Up":
        strong = hl.adx >= config.ADX_TREND
        state = "Strong uptrend" if strong else "Uptrend"
        advice = f"Look for BUYS on pullbacks toward support {sp}. Avoid selling."
        score += 2 + (1 if strong else 0) + (1 if near_sup else 0) - (1 if near_res else 0)
    elif d_dir == "Down" and h_dir == "Down":
        strong = hl.adx >= config.ADX_TREND
        state = "Strong downtrend" if strong else "Downtrend"
        advice = f"Look for SELLS on rallies toward resistance {rp}. Avoid buying."
        score += 2 + (1 if strong else 0) + (1 if near_res else 0) - (1 if near_sup else 0)
    elif hl.regime == "range":
        state = "Ranging"
        advice = f"Range between {sp} and {rp}. Only trade at the edges, or wait for a breakout."
        score += 1 + (1 if (near_sup or near_res) else 0)
    elif d_dir in ("Up", "Down") and h_dir != d_dir:
        state = f"Pullback in {d_dir.lower()}trend"
        advice = (f"Daily trend is {d_dir.lower()} but H4 is against it. Wait for H4 to turn "
                  f"{d_dir.lower()} again before entering.")
        score += 1
    else:
        state, advice = "Mixed", "No clear direction - wait."
    if vol == "quiet":
        advice += " Market is very quiet, so moves may be small."
        score -= 1
    if next_news:
        advice += f" News ahead: {next_news}."
        score -= 1

    return {
        "pair": sym, "price": round(price, digits), "D1 trend": d_dir, "H4 trend": h_dir,
        "H4 ADX": round(hl.adx, 1), "H4 RSI": round(hl.rsi, 1),
        "volatility": f"{vol} ({vol_ratio:.1f}x)", "state": state,
        "support": sp, "sup dist (ATR)": sup["dist_atr"] if sup else None,
        "resistance": rp, "res dist (ATR)": res["dist_atr"] if res else None,
        "next news (24h)": next_news or "", "score": score, "advice": advice,
    }


def scan(live):
    events = news.load_events()
    now = live.server_time()
    rows = [r for r in (analyse_pair(live, s, events, now) for s in live.symbols) if r]
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
