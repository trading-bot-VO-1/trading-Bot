"""
All settings for the forex bot live here.
Change numbers here, not inside the code.
"""
from datetime import datetime

# ---------------------------------------------------------------
# MT5 connection
# Leave LOGIN as None to use whatever account is already logged in
# inside your MT5 terminal (easiest: log in to your demo account there).
# ---------------------------------------------------------------
MT5_PATH = None        # e.g. r"C:\Program Files\MetaTrader 5\terminal64.exe"  (None = auto-detect)
MT5_LOGIN = None       # e.g. 12345678
MT5_PASSWORD = None    # e.g. "your-demo-password"
MT5_SERVER = None      # e.g. "MetaQuotes-Demo"

# Broker server clock. Most forex brokers use "New York close" time:
# UTC+2 in winter, UTC+3 in summer (server midnight = 17:00 New York).
#   "NY_CLOSE" -> that standard (recommended, the downloader prints a check)
#   2 / 3 / 0  -> a fixed UTC offset in hours, if your broker differs
SERVER_TZ = "NY_CLOSE"

# ---------------------------------------------------------------
# Market
# All 28 major + cross pairs. Broker suffixes (EURUSDm, EURUSD.r, ...)
# are detected automatically.
# ---------------------------------------------------------------
SYMBOLS = [
    # majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    # EUR crosses
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
    # GBP crosses
    "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    # AUD / NZD crosses
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD", "NZDJPY", "NZDCHF", "NZDCAD",
    # CAD / CHF crosses
    "CADJPY", "CADCHF", "CHFJPY",
]

TIMEFRAME = "H1"                    # strategies are tuned for H1
START = datetime(2021, 1, 1)        # ~5 years of history
END = None                          # None = up to now
WF_SPLIT = datetime(2024, 1, 1)     # walk-forward: tune before this date, validate after

# ---------------------------------------------------------------
# Strategies - listed in PRIORITY order. If two fire on the same
# candle for the same pair, the first one in this list wins.
# Remove a name to switch that strategy off.
# ---------------------------------------------------------------
STRATEGIES = ["trend", "breakout", "meanrev"]

# --- Regime filter: which market type each strategy may trade in ---
USE_REGIME_FILTER = True
ADX_PERIOD = 14
ADX_TREND = 25          # ADX >= 25  -> "trend"
ADX_RANGE = 20          # ADX <  20  -> "range"; between = "neutral"
REGIME_ALLOWED = {
    "trend":    {"trend"},
    "breakout": {"trend", "neutral"},
    "meanrev":  {"range"},
}
# Volatility gate: skip all trades when ATR is abnormally low or high
VOL_LOOKBACK = 100      # bars used for the "normal" ATR (median)
VOL_MIN_RATIO = 0.5     # ATR below 0.5x normal -> market too dead
VOL_MAX_RATIO = 2.5     # ATR above 2.5x normal -> market too wild

ATR_PERIOD = 14

# --- Strategy 1: trend-following pullback ---
EMA_FAST = 50
EMA_SLOW = 200
TREND_SL_ATR = 1.5      # stop = 1.5 x ATR
TREND_RR = 2.0          # target = 2 x stop
TREND_TRAIL = True

# --- Strategy 2: Asian-range breakout at London open (server-time hours) ---
ASIA_START_HOUR = 0         # range built from 00:00 ...
ASIA_END_HOUR = 9           # ... to 08:59 server time (= Asian session)
BREAKOUT_END_HOUR = 13      # only take breakouts 09:00-12:59 (London morning)
BREAKOUT_BUFFER_ATR = 0.1   # close must clear the range by 0.1 x ATR
BREAKOUT_MAX_RANGE_ATR = 4.0  # skip days where the Asian range is huge
BREAKOUT_SL_MIN_ATR = 1.0   # stop = range height, clamped to 1.0 - 2.5 x ATR
BREAKOUT_SL_MAX_ATR = 2.5
BREAKOUT_RR = 2.0
BREAKOUT_TRAIL = True

# --- Strategy 3: mean reversion (Bollinger + RSI) ---
BB_PERIOD = 20
BB_STD = 2.0
RSI_PERIOD = 14
RSI_LOW = 30
RSI_HIGH = 70
MR_SL_ATR = 1.5
MR_RR = 1.5
MR_TRAIL = False            # mean reversion takes its target, no trailing

# --- Trade management (all strategies) ---
BREAKEVEN_AT_R = 1.0        # move stop to entry once trade is +1R
TRAIL_ATR_MULT = 1.5        # then trail 1.5 x ATR behind price (if strategy trails)

# ---------------------------------------------------------------
# News filter: no new trades around high-impact news for either
# currency of the pair.
# ---------------------------------------------------------------
USE_NEWS_FILTER = True
NEWS_BLOCK_BEFORE_MIN = 60      # no entries from 60 min before ...
NEWS_BLOCK_AFTER_MIN = 30       # ... until 30 min after the event
NEWS_BUILTIN = True             # built-in US NFP + FOMC dates (2021-2026)
NEWS_FILE = "data/news_events.csv"   # optional full calendar (see README)

# ---------------------------------------------------------------
# Risk rules (from the strategy doc)
# ---------------------------------------------------------------
INITIAL_BALANCE = 10_000.0     # backtest starting balance (account currency)
RISK_PER_TRADE = 0.01          # 1% of balance per trade (doc range: 0.5% - 1%)
DAILY_LOSS_LIMIT = 0.03        # stop opening trades for the day after -3%
MAX_DRAWDOWN = 0.10            # pause the bot at -10% from peak balance
MAX_OPEN_TRADES = 3            # across all pairs, one per pair

# ---------------------------------------------------------------
# Costs (keep these realistic or the backtest will lie)
# ---------------------------------------------------------------
COMMISSION_PER_LOT = 7.0       # round-turn commission per 1.0 lot, account currency
USE_HISTORICAL_SPREAD = True   # use the spread stored in MT5 history
MIN_SPREAD_POINTS = 10         # never assume less than this (10 points = 1 pip on 5-digit pairs)

# ---------------------------------------------------------------
# Folders
# ---------------------------------------------------------------
DATA_DIR = "data"
RESULTS_DIR = "results"
