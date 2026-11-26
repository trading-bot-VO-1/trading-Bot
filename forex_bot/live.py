"""
Read-only connection to your MT5 terminal for the advisor.

SAFETY: this module never calls order_send / order_check or anything that
can open, modify or close a trade. It only READS prices, account info,
open positions and trade history.
"""
import threading
import time

import pandas as pd

import config
import mt5_data

TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


class Live:
    def __init__(self, cache_seconds=20):
        self.mt5 = mt5_data.connect()
        self._lock = threading.Lock()
        self._cache = {}
        self._ttl = cache_seconds
        self.broker = {}                       # EURUSD -> EURUSDm
        for name in config.SYMBOLS:
            b = mt5_data.resolve_symbol(self.mt5, name)
            if b:
                self.mt5.symbol_select(b, True)
                self.broker[name] = b
        self.symbols = list(self.broker)
        self._base = {v: k for k, v in self.broker.items()}

    # ---------- helpers ----------
    def base(self, broker_symbol):
        return self._base.get(broker_symbol, broker_symbol[:6])

    def _cached(self, key, fn):
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        with self._lock:
            val = fn()
        self._cache[key] = (now, val)
        return val

    # ---------- market data ----------
    def bars(self, name, tf, n=None):
        """CLOSED candles only (the still-forming candle is dropped)."""
        n = n or config.ADVISOR_BARS

        def fetch():
            rates = self.mt5.copy_rates_from_pos(self.broker[name],
                                                 getattr(self.mt5, f"TIMEFRAME_{tf}"), 0, n + 1)
            if rates is None or len(rates) < 2:
                return None
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            return df.iloc[:-1][["time", "open", "high", "low", "close", "tick_volume", "spread"]] \
                .reset_index(drop=True)
        return self._cached(("bars", name, tf, n), fetch)

    def tick(self, name):
        with self._lock:
            t = self.mt5.symbol_info_tick(self.broker[name])
        if t is None:
            return None
        return {"bid": t.bid, "ask": t.ask, "time": pd.Timestamp(t.time, unit="s")}

    def spec(self, name):
        def fetch():
            return mt5_data._spec(self.mt5.symbol_info(self.broker[name]))
        return self._cached(("spec", name), fetch)

    def server_time(self):
        for name in self.symbols[:3]:
            t = self.tick(name)
            if t:
                return t["time"]
        return pd.Timestamp.utcnow().tz_localize(None)

    # ---------- account ----------
    def account(self):
        with self._lock:
            a = self.mt5.account_info()
        return a._asdict() if a else {}

    def positions(self):
        with self._lock:
            pos = self.mt5.positions_get() or []
        out = []
        for p in pos:
            d = p._asdict()
            d["base"] = self.base(d["symbol"])
            d["direction"] = 1 if d["type"] == 0 else -1
            out.append(d)
        return out

    def deals(self, date_from, date_to):
        with self._lock:
            deals = self.mt5.history_deals_get(pd.Timestamp(date_from).to_pydatetime(),
                                               pd.Timestamp(date_to).to_pydatetime())
        if not deals:
            return pd.DataFrame()
        df = pd.DataFrame([d._asdict() for d in deals])
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df["base"] = df["symbol"].map(lambda s: self.base(s) if s else "")
        return df

    def position_sl(self, position_id):
        """Initial stop-loss of a closed position (from its order history), or None."""
        with self._lock:
            orders = self.mt5.history_orders_get(position=position_id)
        for o in sorted(orders or [], key=lambda o: o.time_setup):
            if o.sl:
                return o.sl
        return None
