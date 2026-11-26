"""
Connects to MetaTrader 5, downloads candles for every pair and caches them
to CSV, so later backtests run without MT5 open.
"""
import json
import os
from datetime import datetime

import pandas as pd

import config

TF_NAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


def connect():
    """Open the MT5 terminal connection. Returns the MetaTrader5 module."""
    import MetaTrader5 as mt5  # only works on Windows with MT5 installed

    kwargs = {}
    if config.MT5_PATH:
        kwargs["path"] = config.MT5_PATH
    if config.MT5_LOGIN:
        kwargs.update(login=int(config.MT5_LOGIN),
                      password=config.MT5_PASSWORD,
                      server=config.MT5_SERVER)

    if not mt5.initialize(**kwargs):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    acc = mt5.account_info()
    if acc is None:
        raise RuntimeError("Connected to MT5 but no account is logged in.")
    print(f"Connected: account {acc.login} on {acc.server} "
          f"| balance {acc.balance} {acc.currency}")
    return mt5


def resolve_symbol(mt5, name):
    """Find the broker's symbol for a pair name (handles suffixes like EURUSDm)."""
    if mt5.symbol_info(name) is not None:
        return name
    candidates = mt5.symbols_get(group=f"{name}*") or []
    names = sorted((s.name for s in candidates), key=len)
    return names[0] if names else None


def _spec(info):
    return {
        "broker_symbol": info.name,
        "digits": info.digits,
        "point": info.point,
        "tick_size": info.trade_tick_size,
        "tick_value": info.trade_tick_value,   # value of 1 tick for 1 lot, account currency
        "volume_min": info.volume_min,
        "volume_max": info.volume_max,
        "volume_step": info.volume_step,
        "contract_size": info.trade_contract_size,
    }


def check_server_clock(mt5, symbol):
    """Print the broker's UTC offset so you can confirm config.SERVER_TZ.
    Only reliable while the market is open (Mon-Fri)."""
    import time
    from zoneinfo import ZoneInfo

    sym = resolve_symbol(mt5, symbol)
    if sym is None:
        return
    mt5.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return
    offset = round((tick.time - time.time()) / 3600)
    now = datetime.now(ZoneInfo("UTC"))
    ny_dst = bool(now.astimezone(ZoneInfo("America/New_York")).dst())
    expected = 3 if ny_dst else 2
    print(f"Broker server clock: UTC{offset:+d} "
          f"(NY_CLOSE standard right now = UTC+{expected})")
    if config.SERVER_TZ == "NY_CLOSE" and offset != expected:
        print("  !! Your broker does not look like NY_CLOSE time. If the market is open, "
              f"set SERVER_TZ = {offset} in config.py (news + breakout times depend on it).")


def csv_path(symbol, timeframe):
    return os.path.join(config.DATA_DIR, f"{symbol}_{timeframe}.csv")


def specs_path():
    return os.path.join(config.DATA_DIR, "specs.json")


def download(symbols=None, timeframe=None, start=None, end=None):
    """Download candles from MT5 and save them to data/."""
    symbols = symbols or config.SYMBOLS
    timeframe = timeframe or config.TIMEFRAME
    start = start or config.START
    end = end or config.END or datetime.now()

    os.makedirs(config.DATA_DIR, exist_ok=True)
    mt5 = connect()
    tf = getattr(mt5, f"TIMEFRAME_{timeframe}")

    check_server_clock(mt5, symbols[0])

    specs = {}
    if os.path.exists(specs_path()):
        with open(specs_path()) as f:
            specs = json.load(f)

    try:
        for name in symbols:
            broker_sym = resolve_symbol(mt5, name)
            if broker_sym is None:
                print(f"  {name}: not offered by this broker, skipped")
                continue
            mt5.symbol_select(broker_sym, True)
            rates = mt5.copy_rates_range(broker_sym, tf, start, end)
            if rates is None or len(rates) == 0:
                print(f"  {name}: no data ({mt5.last_error()}). "
                      "Tip: MT5 > Tools > Options > Charts > Max bars = Unlimited")
                continue
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df[["time", "open", "high", "low", "close", "tick_volume", "spread"]]
            df.to_csv(csv_path(name, timeframe), index=False)
            specs[name] = _spec(mt5.symbol_info(broker_sym))
            print(f"  {name} ({broker_sym}): {len(df)} bars "
                  f"{df.time.iloc[0]:%Y-%m-%d} -> {df.time.iloc[-1]:%Y-%m-%d}")
    finally:
        mt5.shutdown()

    with open(specs_path(), "w") as f:
        json.dump(specs, f, indent=2)
    return specs


def load(symbols=None, timeframe=None, start=None, end=None):
    """Load cached candles + symbol specs from data/. Returns (data, specs)."""
    symbols = symbols or config.SYMBOLS
    timeframe = timeframe or config.TIMEFRAME
    if not os.path.exists(specs_path()):
        raise FileNotFoundError("No cached data. Run: python run_backtest.py --download")
    with open(specs_path()) as f:
        specs = json.load(f)

    data = {}
    for name in symbols:
        path = csv_path(name, timeframe)
        if name not in specs or not os.path.exists(path):
            print(f"  {name}: no cached data, skipped")
            continue
        df = pd.read_csv(path, parse_dates=["time"])
        if start is not None:
            df = df[df.time >= pd.Timestamp(start)]
        if end is not None:
            df = df[df.time <= pd.Timestamp(end)]
        data[name] = df.reset_index(drop=True)
    return data, {k: v for k, v in specs.items() if k in data}
