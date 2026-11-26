# Forex Bot — Backtest Suite (MT5 + Python)

Backtests **3 strategies** on all 28 major and cross forex pairs, using one shared account, the risk rules from the strategy doc, a **regime filter**, a **news filter** and **walk-forward testing**.

It never places real trades. It tells you whether the system would have made money.

---

## Strategies (`strategies/`)

| Strategy | Market type | Entry | Stop / Target | Trailing |
|---|---|---|---|---|
| **trend** | Trending (ADX ≥ 25) | EMA50/200 trend + candle wicks to EMA50 and bounces | 1.5×ATR / 2R | Yes |
| **breakout** | Trend or neutral | First H1 close beyond the Asian range (00:00–08:59 server) during 09:00–12:59 | Range height (1–2.5×ATR) / 2R | Yes |
| **meanrev** | Ranging (ADX < 20) | Close outside Bollinger(20,2) + RSI < 30 / > 70 | 1.5×ATR / 1.5R | No |

All signals come from a **closed** candle and enter at the **next** candle's open, so there's no look-ahead.

**Regime filter** (`strategies/combine.py`): each strategy only trades in its market type (see `REGIME_ALLOWED` in `config.py`). All trades are skipped when ATR is below 0.5× or above 2.5× its normal level. If two strategies fire together, the one listed first in `config.STRATEGIES` wins.

## Risk rules (`backtest.py`)

- 1% risk per trade (lot size calculated from the stop distance)
- Max 3 open trades across all pairs, one per pair
- No new trades after a 3% loss in a day
- Bot pauses at a 10% drawdown from the peak
- Stop moves to breakeven at +1R, then a 1.5×ATR trailing stop (trend and breakout)
- Real spread from MT5 history (minimum 1 pip) plus $7/lot commission
- Stop and target in the same candle counts as a stop (pessimistic)

## News filter (`news.py`)

No new trades from **60 min before to 30 min after** a high-impact event for either currency of the pair. An NFP release blocks EURUSD but not EURGBP, for example.

Event sources:
1. **Built-in:** US Non-Farm Payrolls and FOMC decisions for 2021–2026. These cover the biggest movers.
2. **`data/news_events.csv`:** add any full calendar here, such as an export from Forex Factory or Investing.com. Required columns:
   ```
   time_utc,currency,impact,title
   2024-03-07 13:15,EUR,High,ECB Rate Decision
   ```
   Only `High` impact rows are used. Times must be **UTC**.
3. **`python news.py --update`:** downloads **this week's** Forex Factory calendar and appends it to that file. Run it weekly and your history builds up; the live bot will use the same function. `python news.py --show` lists the loaded events.

> Until you add a full historical calendar, the backtest only filters NFP and FOMC. Other events (CPI, ECB, BoE and so on) are filtered only from the date you start collecting them.

## Server time (important)

MT5 candles use your **broker's server clock**, and the news times and Asian-session hours depend on it. Most brokers use **"NY close" time** (UTC+2 in winter, UTC+3 in summer), which is the default `SERVER_TZ = "NY_CLOSE"`.

`--download` prints your broker's offset while the market is open. If it warns you, set `SERVER_TZ` to the fixed number it shows (for example `0` or `2`).

---

## Setup (Windows)

1. Install **MetaTrader 5**, open it and log in to a **demo account**.
2. In MT5, go to **Tools → Options → Charts** and set **Max bars in chart = Unlimited**.
3. Copy this folder into your repo, then run:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
   Use Python 3.11 or 3.12.

## Run

```
python run_backtest.py --download                 # first run: pull data from MT5 (keep MT5 open)
python run_backtest.py                            # rerun on cached data after changing config.py
python run_backtest.py --walk-forward             # tune on 2021-2023, validate on 2024+
python run_backtest.py --strategies trend         # test one strategy alone
python run_backtest.py --strategies trend,breakout
python run_backtest.py --symbols EURUSD,GBPJPY
python run_backtest.py --no-news --no-regime      # see what the filters add
python run_backtest.py --no-pause                 # ignore the 10% pause to see the whole period
```

## Output (`results/<date_time>/`)

| File | What it shows |
|---|---|
| `summary.txt` | Totals, then tables per strategy, per year and per pair |
| `trades.csv` | Every trade: strategy, entry/exit, lots, reason (SL/TP/BE/TRAIL), P&L, R |
| `per_strategy.csv` / `per_year.csv` / `per_symbol.csv` | Same tables as CSV |
| `equity.png` | Equity curve and drawdown |
| `walk_forward.txt` | In-sample vs out-of-sample comparison (with `--walk-forward`) |

## How to read results

Suggested order:
1. `--no-pause` with all strategies shows the full picture.
2. Look at the **per-strategy** table. Turn off any strategy with a profit factor below 1.1 (`--strategies ...`).
3. Look at the **per-pair** table. Remove pairs that lose money from `SYMBOLS`, deciding on **2021–2023 data only**.
4. Run `--walk-forward`. If the out-of-sample results hold up, the edge is likely real.

Ready for the live demo phase only if **all** of these hold:
- Profit factor > 1.3 overall and > 1.2 out-of-sample
- Max drawdown < 15%
- 200+ trades
- Profitable in most years

## Known limits

- **Lot value conversion** uses each pair's *current* tick value from MT5. This is exact for xxxUSD pairs and approximate for crosses and JPY pairs, which is fine for research.
- **NFP dates are rule-based:** first Friday, and when that falls on the 1st–3rd, the next Friday is blocked too. FOMC dates are exact.
- The daily loss limit uses realised balance and resets at server midnight.

## Files

| File | Purpose |
|---|---|
| `config.py` | Every setting |
| `mt5_data.py` | MT5 connection, server clock check, data download and cache |
| `indicators.py` | EMA, ATR, ADX, RSI, Bollinger (MT5-style formulas) |
| `strategies/trend.py`, `breakout.py`, `meanrev.py` | Signal rules |
| `strategies/combine.py` | Regime and volatility filter, strategy priority |
| `news.py` | News calendar and filter, Forex Factory weekly update |
| `backtest.py` | Portfolio engine with the risk rules |
| `report.py` | Stats, tables, chart, walk-forward comparison |
| `run_backtest.py` | Command-line entry point |

## Next

Live executor on an MT5 demo account: order placement, live breakeven and trailing, automatic news updates, Telegram alerts and kill switch, logging, and a Windows VPS.
