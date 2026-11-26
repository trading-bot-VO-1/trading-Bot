# Forex Advisor (MT5 + Python)

A **trading advisor** for MetaTrader 5. It tells you what each pair is doing, which trades meet the rules, where to place the entry, stop-loss and take-profit, and what lot size to use for your balance. Then it tracks how your own trades perform.

> **It never places, changes or closes a trade.** It only reads prices, your balance, open positions and trade history from MT5. You make every decision and place every order yourself.

---

## Quick start (Windows)

1. Open **MetaTrader 5** and log in (e.g. Exness demo `Exness-MT5Trial16`). Keep it open.
2. In the project folder:
   ```powershell
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. **Run the strategy lab once** (5–15 min). It decides which strategies may send signals:
   ```powershell
   python lab.py
   ```
4. **Start the dashboard.** It opens in your browser at http://localhost:8501:
   ```powershell
   streamlit run dashboard.py
   ```

Optional: `python run_advisor.py` runs the same checks in the terminal and sends Telegram alerts (see *Alerts* below).

---

## Dashboard tabs

| Tab | What it gives you |
|---|---|
| 🎯 **Signals** | Trade signals from **approved** strategies: pair, BUY/SELL, entry, stop-loss, take-profit, pips, **lot size for your balance**, money at risk, reward:risk, the reason, how to manage the trade, the setup's backtest record on that pair, and warnings. When nothing qualifies it says **"No trade right now."** |
| 🔎 **Market scanner** | All 28 pairs: D1 and H4 trend, trending/ranging/volatile, ADX, RSI, nearest support and resistance, news in the next 24h, and plain-English advice, e.g. *"Strong uptrend: look for BUYS on pullbacks toward support 1.0820. Avoid selling."* Ranked best-to-worst conditions, with an *Avoid for now* list. |
| 🧮 **Lot calculator** | For your own trade ideas: pick pair, direction, entry and stop. It gives the exact lot size for your risk %, the pip distance, reward:risk, and warnings. |
| 📂 **Open trades** | Your live positions, trades **without a stop-loss** (flagged red), and net exposure per currency. |
| 📓 **Journal** | Every closed trade from MT5 history: P&L, R-multiple, win rate, profit factor, results by pair, and **advisor signals vs your own ideas**. |
| 🧪 **Strategy lab** | Which strategies are approved or rejected, and why. |
| 📰 **News** | High-impact events for the next 7 days, with a one-click update from Forex Factory. |

**Sidebar:** balance, equity, today's P&L, the **daily-loss lock** (red banner at −3%: stop trading for the day), risk-per-trade slider, auto-refresh rate, and a *Show unproven setups* toggle.

---

## How signals are decided

### 1. Only approved strategies can send a "TAKE" signal
`lab.py` walk-forward tests every strategy on your broker's data with real spread:

- **2021–2023** (in-sample) and **2024–now** (out-of-sample, unseen)
- **Approved** only if profit factor ≥ **1.2 in both periods**, ≥ 100 trades total and ≥ 30 in 2024+

A strategy that fails never produces a TAKE signal. **If none pass, the advisor shows analysis but no signals.** That's deliberate: a signal without a proven edge is just a guess. Re-run `python lab.py` once a month.

### 2. The strategies

| Strategy | Timeframe | Setup |
|---|---|---|
| `mtf` | H4 | **Multi-timeframe confluence:** D1 uptrend (above a rising daily EMA50) + H4 pullback (RSI < 40) + H4 closes back above EMA20. Mirror for sells. |
| `sr_bounce` | H4 | **Support/resistance rejection:** D1 trend + pin-bar rejection at the latest confirmed swing low (buy) or high (sell). |
| `donchian` | D1 | 55-day breakout, exit on the 20-day channel (Turtle style) |
| `trend` | H1 | EMA50/200 trend + pullback to EMA50, ADX ≥ 25 |
| `breakout` | H1 | Asian-range breakout at the London open |
| `meanrev` | H1 | Bollinger Band + RSI extremes in ranging markets |

Results on Exness data so far (with costs): `trend`, `breakout`, `meanrev` and `donchian` **failed** (profit factor 0.53–0.98). `mtf` and `sr_bounce` are new and untested on real data. Run `lab.py` to see their results.

### 3. Every signal is checked against your account
A signal turns into **SKIP** (with the reason) when:
- the **daily-loss lock** is on (−3% today)
- you already have **3 open trades**, or a trade on that pair
- it would put **more than 2 same-direction trades on one currency**
- **high-impact news** for that pair is due within the next hour (or was 30 min ago)
- the account is too small for the stop at your risk %

### 4. Signals expire
A signal is valid until the next candle of its timeframe closes. After that it disappears; don't chase it.

---

## Alerts (optional, Telegram)
1. In Telegram, message **@BotFather**, send `/newbot` and copy the **token**.
2. Message **@userinfobot** and copy your **chat id**. Also send any message to your new bot once.
3. Put both into `config.py`: `TELEGRAM_TOKEN = "..."`, `TELEGRAM_CHAT_ID = "..."`
4. Run `python run_advisor.py`. New **TAKE** signals are sent to your phone.

Without Telegram, the dashboard shows a pop-up when a new signal appears.

---

## Settings (`config.py`)
- **Broker:** `SERVER_TZ = 0`, `SYMBOL_SUFFIX = "m"` (Exness). Other brokers: usually `SERVER_TZ = "NY_CLOSE"` and their own suffix.
- **Risk:** `RISK_PER_TRADE`, `DAILY_LOSS_LIMIT`, `MAX_OPEN_TRADES`, `MAX_SAME_CURRENCY`
- **Lab rules:** `LAB_MIN_PF`, `LAB_MIN_TRADES`, `LAB_MIN_OOS_TRADES`, `LAB_STRATEGIES`
- **News window:** `NEWS_BLOCK_BEFORE_MIN`, `NEWS_BLOCK_AFTER_MIN`
- Each strategy's parameters are in its own section.

---

## Research tools (backtesting)
```powershell
python run_backtest.py --timeframe H4 --strategies mtf --no-pause
python run_backtest.py --timeframe H4 --strategies sr_bounce --walk-forward
python run_backtest.py --download          # refresh price data
python news.py --update                    # add this week's Forex Factory calendar
```
Results are saved in `results/`. The backtester uses the same strategy code as the advisor, so backtest signals and live signals are identical.

---

## Files

| File | Purpose |
|---|---|
| `dashboard.py` | Streamlit dashboard |
| `run_advisor.py` | Terminal advisor + Telegram alerts |
| `advisor.py` | Signal engine (entry/SL/TP, lots, warnings) |
| `scanner.py` | Market state for all pairs |
| `risk.py` | Lot size, daily-loss lock, exposure checks |
| `journal.py` | Your closed trades from MT5 history |
| `lab.py` | Strategy lab: approves strategies for signals |
| `live.py` | Read-only MT5 connection |
| `levels.py` | Support/resistance zones |
| `news.py`, `alerts.py` | News calendar, Telegram |
| `strategies/` | All strategy rules + regime filter |
| `backtest.py`, `run_backtest.py`, `report.py`, `mt5_data.py`, `indicators.py` | Backtesting engine |

---

## Important
- Trading forex with leverage can lose more than you expect. Backtest results don't guarantee future results.
- Use a **demo account** until a strategy is approved **and** has worked on demo for at least 4–8 weeks.
- This tool is decision support, not financial advice.
