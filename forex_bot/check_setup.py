"""
Diagnostic: times each part of the advisor OUTSIDE Streamlit, to find what is slow or stuck.

    python check_setup.py

Keep MT5 open and logged in. Paste the full output to get help.
"""
import sys
import time

t0 = time.time()


def step(name):
    print(f"[{time.time() - t0:6.1f}s] {name} ...", flush=True)


step("importing libraries")
import pandas as pd  # noqa: E402
import config  # noqa: E402
import MetaTrader5  # noqa: E402,F401

step("connecting to MT5 (if this hangs: open MT5 and log in)")
from live import Live  # noqa: E402
live = Live()
print(f"         pairs found: {len(live.symbols)}  e.g. {list(live.broker.items())[:2]}", flush=True)

step("reading price + server time")
print(f"         server time {live.server_time()}  EURUSD {live.tick(live.symbols[0])}", flush=True)

step("downloading candles for 1 pair (D1, H4, H1)")
for tf in ("D1", "H4", "H1"):
    b = live.bars(live.symbols[0], tf)
    print(f"         {tf}: {0 if b is None else len(b)} bars", flush=True)

step("daily-loss status")
import risk  # noqa: E402
print(f"         {risk.daily_status(live)}", flush=True)

step("market scanner (28 pairs)")
import scanner  # noqa: E402
sc = scanner.scan(live)
print(f"         {len(sc)} pairs scanned. Top: {sc.pair.head(3).tolist() if len(sc) else '-'}", flush=True)

step("signals")
import advisor  # noqa: E402
sig, _ = advisor.find_signals(live)
print(f"         {len(sig)} signal(s)", flush=True)

step("journal (trade history)")
import journal  # noqa: E402
tr = journal.closed_trades(live)
print(f"         {len(tr)} closed trade(s)", flush=True)

step("streamlit import")
import streamlit  # noqa: E402
print(f"         streamlit {streamlit.__version__}, python {sys.version.split()[0]}", flush=True)

step("ALL OK - everything works outside the dashboard")
