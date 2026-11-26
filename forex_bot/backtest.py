"""
Portfolio backtest engine.

Runs every pair on one shared timeline with one shared account, so the
portfolio-level risk rules work exactly as they will live:
  - risk % of balance per trade (lot size from stop distance)
  - max open trades across all pairs, one trade per pair
  - daily loss limit (no new trades for the rest of the day)
  - max drawdown pause (bot stops opening trades)
  - news filter (no entries around high-impact events)
  - breakeven at +1R, then ATR trailing stop (for strategies that trail)

Execution model (conservative):
  - MT5 candles are BID prices. Buys fill at ASK = bid + spread.
  - Signal on candle close -> entry at next candle open.
  - If stop and target are both inside one candle, the STOP is assumed hit first.
  - Breakeven / trailing updates use the candle close and apply from the next candle.
  - Commission charged per lot on exit.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config
import news
from strategies import combine

NS_PER_DAY = 86_400_000_000_000


@dataclass
class Position:
    symbol: str
    strategy: str
    direction: int          # 1 long, -1 short
    entry_time: pd.Timestamp
    entry_price: float
    sl: float
    tp: float
    lots: float
    risk_amount: float
    r_dist: float           # initial stop distance in price
    trail: str              # "atr", "none" or "channel"
    stop_kind: str = "SL"   # SL -> BE -> TRAIL


class Backtester:
    def __init__(self, data, specs, cfg=config):
        self.cfg = cfg
        self.specs = specs
        events = news.load_events() if cfg.USE_NEWS_FILTER else None
        self.arrays = {}
        for sym, df in data.items():
            p = combine.prepare(df, cfg)
            blocked = (news.block_mask(sym, p["time"].values, events)
                       if cfg.USE_NEWS_FILTER else np.zeros(len(p), dtype=bool))
            self.arrays[sym] = {
                "t": p["time"].values.astype("datetime64[ns]").astype(np.int64),
                "open": p["open"].values, "high": p["high"].values,
                "low": p["low"].values, "close": p["close"].values,
                "spread": p["spread"].values if "spread" in p else np.zeros(len(p)),
                "atr": p["atr"].values, "adx": p["adx"].values,
                "signal": p["signal"].values, "sl_dist": p["sl_dist"].values,
                "tp_dist": p["tp_dist"].values, "strategy": p["strategy"].values,
                "trail": p["trail"].values, "exit_lo": p["exit_lo"].values,
                "exit_hi": p["exit_hi"].values, "news": blocked, "n": len(p),
            }

    # ---------- helpers ----------
    def _money(self, sym, price_diff, lots):
        s = self.specs[sym]
        return price_diff / s["tick_size"] * s["tick_value"] * lots

    def _spread(self, sym, i):
        pts = self.arrays[sym]["spread"][i] if self.cfg.USE_HISTORICAL_SPREAD else 0
        return max(pts, self.cfg.MIN_SPREAD_POINTS) * self.specs[sym]["point"]

    def _lot_size(self, sym, sl_dist):
        s = self.specs[sym]
        risk_amount = self.balance * self.cfg.RISK_PER_TRADE
        loss_per_lot = self._money(sym, sl_dist, 1.0)
        if loss_per_lot <= 0:
            return 0.0, 0.0
        lots = risk_amount / loss_per_lot
        step = s["volume_step"]
        lots = np.floor(lots / step + 1e-9) * step
        lots = min(lots, s["volume_max"])
        if lots < s["volume_min"]:
            return 0.0, 0.0
        return round(lots, 2), self._money(sym, sl_dist, lots)

    # ---------- trade lifecycle ----------
    def _open(self, sym, i, ts):
        a = self.arrays[sym]
        j = i - 1                                   # signal candle
        direction = int(a["signal"][j])
        sl_dist, tp_dist = a["sl_dist"][j], a["tp_dist"][j]
        if not (np.isfinite(sl_dist) and sl_dist > 0 and np.isfinite(tp_dist)):
            return
        lots, risk_amount = self._lot_size(sym, sl_dist)
        if lots <= 0:
            return
        bid = a["open"][i]
        entry = bid + self._spread(sym, i) if direction == 1 else bid
        pos = Position(sym, a["strategy"][j], direction, ts, entry,
                       sl=entry - direction * sl_dist, tp=entry + direction * tp_dist,
                       lots=lots, risk_amount=risk_amount, r_dist=sl_dist,
                       trail=str(a["trail"][j]))
        self.positions[sym] = pos
        self._check_exit(pos, i, ts)   # stop/target can be hit on the entry candle

    def _check_exit(self, pos, i, ts):
        a = self.arrays[pos.symbol]
        # longs exit at bid; shorts exit at ask
        sp = 0.0 if pos.direction == 1 else self._spread(pos.symbol, i)
        o, h, l = a["open"][i] + sp, a["high"][i] + sp, a["low"][i] + sp

        price, reason = None, None
        if pos.direction == 1:
            if o <= pos.sl:   price, reason = o, pos.stop_kind
            elif o >= pos.tp: price, reason = o, "TP"
            elif l <= pos.sl: price, reason = pos.sl, pos.stop_kind
            elif h >= pos.tp: price, reason = pos.tp, "TP"
        else:
            if o >= pos.sl:   price, reason = o, pos.stop_kind
            elif o <= pos.tp: price, reason = o, "TP"
            elif h >= pos.sl: price, reason = pos.sl, pos.stop_kind
            elif l <= pos.tp: price, reason = pos.tp, "TP"

        if price is not None:
            self._close(pos, price, ts, reason)

    def _close(self, pos, price, ts, reason):
        gross = self._money(pos.symbol, pos.direction * (price - pos.entry_price), pos.lots)
        commission = self.cfg.COMMISSION_PER_LOT * pos.lots
        pnl = gross - commission
        self.balance += pnl
        self.trades.append({
            "symbol": pos.symbol, "strategy": pos.strategy,
            "direction": "BUY" if pos.direction == 1 else "SELL",
            "entry_time": pos.entry_time, "entry_price": pos.entry_price,
            "sl_initial": pos.entry_price - pos.direction * pos.r_dist, "tp": pos.tp,
            "exit_time": ts, "exit_price": price, "lots": pos.lots,
            "reason": reason, "commission": round(commission, 2),
            "pnl": round(pnl, 2), "r_multiple": round(pnl / pos.risk_amount, 2),
            "balance_after": round(self.balance, 2),
        })
        del self.positions[pos.symbol]

    def _manage(self, pos, i):
        """Breakeven and trailing, decided on candle close, active from next candle."""
        a = self.arrays[pos.symbol]
        close, atr_now = a["close"][i], a["atr"][i]
        d = pos.direction

        if pos.trail == "channel":          # Donchian exit: stop follows the 20-day channel
            level = a["exit_lo"][i] if d == 1 else a["exit_hi"][i]
            if pos.direction == -1:
                level += self._spread(pos.symbol, i)   # shorts exit at ask
            if np.isfinite(level) and d * (level - pos.sl) > 0:
                pos.sl = level
                pos.stop_kind = "TRAIL" if d * (pos.sl - pos.entry_price) > 0 else "CHANNEL"
            return

        profit = d * (close - pos.entry_price)

        if pos.stop_kind == "SL" and profit >= self.cfg.BREAKEVEN_AT_R * pos.r_dist:
            pos.sl = pos.entry_price
            pos.stop_kind = "BE"
        if pos.trail == "atr" and pos.stop_kind in ("BE", "TRAIL"):
            trail = close - d * self.cfg.TRAIL_ATR_MULT * atr_now
            if d * (trail - pos.sl) > 0:
                pos.sl = trail
                if d * (pos.sl - pos.entry_price) > 0:
                    pos.stop_kind = "TRAIL"

    def _floating(self):
        total = 0.0
        for sym, pos in self.positions.items():
            price = self.last_close[sym]
            total += self._money(sym, pos.direction * (price - pos.entry_price), pos.lots)
        return total

    # ---------- main loop ----------
    def run(self, trade_start=None, trade_end=None):
        """Indicators use all loaded history; trading happens only in [trade_start, trade_end]."""
        cfg = self.cfg
        self.balance = cfg.INITIAL_BALANCE
        self.positions, self.trades, self.events = {}, [], []
        self.last_close = {}
        self.news_skips = 0
        equity_rows = []

        t0 = pd.Timestamp(trade_start).value if trade_start is not None else None
        t1 = pd.Timestamp(trade_end).value if trade_end is not None else None

        peak = self.balance
        paused = False
        cur_day, day_start, daily_blocked = None, self.balance, False

        all_t = np.unique(np.concatenate([a["t"] for a in self.arrays.values()]))
        ptr = {s: 0 for s in self.arrays}
        ts = None

        for t in all_t:
            bars = {}
            for s, a in self.arrays.items():
                p = ptr[s]
                if p < a["n"] and a["t"][p] == t:
                    bars[s] = p
                    ptr[s] = p + 1
            if t0 is not None and t < t0:
                continue
            if t1 is not None and t > t1:
                break
            ts = pd.Timestamp(t)

            day = t // NS_PER_DAY
            if day != cur_day:
                cur_day, day_start, daily_blocked = day, self.balance, False

            # 1) exits on positions opened earlier
            for s, i in bars.items():
                if s in self.positions:
                    self._check_exit(self.positions[s], i, ts)

            # 2) risk rules
            peak = max(peak, self.balance)
            if not paused and self.balance <= peak * (1 - cfg.MAX_DRAWDOWN):
                paused = True
                self.events.append((ts, f"MAX DRAWDOWN hit ({cfg.MAX_DRAWDOWN:.0%}) - bot paused"))
            if not daily_blocked and self.balance <= day_start * (1 - cfg.DAILY_LOSS_LIMIT):
                daily_blocked = True
                self.events.append((ts, "Daily loss limit hit - no new trades today"))

            # 3) entries (strongest ADX first)
            if not paused and not daily_blocked:
                cands = []
                for s, i in bars.items():
                    a = self.arrays[s]
                    if i > 0 and a["signal"][i - 1] != 0 and s not in self.positions:
                        if a["news"][i]:
                            self.news_skips += 1
                            continue
                        cands.append((a["adx"][i - 1], s, i))
                for _, s, i in sorted(cands, reverse=True):
                    if len(self.positions) >= cfg.MAX_OPEN_TRADES:
                        break
                    self._open(s, i, ts)

            # 4) manage open trades on candle close
            for s, i in bars.items():
                self.last_close[s] = self.arrays[s]["close"][i]
                if s in self.positions:
                    self._manage(self.positions[s], i)

            equity_rows.append((ts, self.balance, self.balance + self._floating()))

        # close anything still open at the last price
        for s in list(self.positions):
            self._close(self.positions[s], self.last_close[s], ts, "END")

        self.equity = pd.DataFrame(equity_rows, columns=["time", "balance", "equity"])
        self.trades_df = pd.DataFrame(self.trades)
        return self
