"""
Forex Advisor dashboard (runs locally in your browser).

    streamlit run dashboard.py

Keep MT5 open and logged in. This tool NEVER places trades - it only reads
your MT5 data and tells you what it sees.
"""
import pandas as pd
import streamlit as st

import advisor
import config
import journal
import lab as lab_mod
import news
import risk
import scanner
from live import Live

st.set_page_config(page_title="Forex Advisor", page_icon="📈", layout="wide")


@st.cache_resource(show_spinner="Connecting to MT5...")
def get_live():
    return Live()


try:
    live = get_live()
except Exception as e:
    st.error(f"Could not connect to MT5: {e}")
    st.info("Open MetaTrader 5, log in to your account, then refresh this page.")
    st.stop()


# ---------------- sidebar ----------------
with st.sidebar:
    st.title("📈 Forex Advisor")
    st.caption("Signals only - you place every trade yourself.")
    acct = live.account()
    st.metric("Balance", f"{acct.get('balance', 0):,.2f} {acct.get('currency', '')}")
    st.metric("Equity", f"{acct.get('equity', 0):,.2f}",
              f"{acct.get('equity', 0) - acct.get('balance', 0):+,.2f}")
    st.caption(f"Account {acct.get('login')} · {acct.get('server')}")

    st.divider()
    day = risk.daily_status(live)
    st.metric("Today", f"{day['pnl_today']:+,.2f}", f"{day['pnl_today_pct']:+.2f}%")
    if day["locked"]:
        st.error(f"🔒 DAILY LOSS LIMIT HIT ({config.DAILY_LOSS_LIMIT:.0%}). Stop trading for today.")
    else:
        st.success(f"Room before daily lock: {day['loss_room']:,.2f}")

    st.divider()
    risk_pct = st.slider("Risk per trade (%)", 0.25, 2.0, config.RISK_PER_TRADE * 100, 0.25)
    config.ADVISOR_RISK = risk_pct / 100
    show_unproven = st.toggle("Show unproven setups (study only)", value=False,
                              help="Setups from strategies that FAILED the lab test. "
                                   "For learning - not for trading.")
    refresh = st.select_slider("Auto-refresh", options=[30, 60, 120, 300],
                               value=config.REFRESH_SECONDS, format_func=lambda s: f"{s}s")
    now = live.server_time()
    st.caption(f"Server time {now:%a %H:%M} · Sessions: {', '.join(scanner.active_sessions(now)) or 'none'}")


tabs = st.tabs(["🎯 Signals", "🔎 Market scanner", "🧮 Lot calculator",
                "📂 Open trades", "📓 Journal", "🧪 Strategy lab", "📰 News"])


# ---------------- signals ----------------
def signal_card(s):
    color = {"TAKE": "green", "SKIP": "orange", "STUDY ONLY": "gray"}[s["status"]]
    with st.container(border=True):
        st.markdown(f"### :{color}[{s['status']}] · {'🟢' if s['direction'] == 'BUY' else '🔴'} "
                    f"**{s['direction']} {s['symbol']}**  \n"
                    f"<small>{s['strategy']} · {s['timeframe']} · valid until "
                    f"{s['valid_until']:%a %H:%M} server time</small>", unsafe_allow_html=True)
        c = st.columns(6)
        c[0].metric("Entry", s["entry"])
        c[1].metric("Stop-loss", s["sl"], f"{s['sl_pips']} pips", delta_color="off")
        c[2].metric("Take-profit", s["tp"] if s["tp"] else "Channel exit",
                    f"{s['tp_pips']} pips" if s["tp"] else None, delta_color="off")
        c[3].metric("Lot size", s["lots"])
        c[4].metric("Risk", f"{s['risk_money']:,.2f}", f"{s['risk_pct']:.2f}%", delta_color="off")
        c[5].metric("Reward : Risk", f"{s['rr']} : 1" if s["rr"] else "open")
        st.markdown(f"**Why:** {s['reason']}  \n**How to manage:** {s['manage']}")
        if s["stats"]:
            st.caption(f"Backtest on {s['symbol']}: {s['stats']['trades']} trades · win "
                       f"{s['stats']['win_rate']}% · profit factor {s['stats']['profit_factor']}")
        for w in s["warnings"]:
            st.warning(w)
        if s["status"] == "STUDY ONLY":
            st.caption("⚠️ This strategy failed the lab test. Study the setup, don't trade it.")


@st.fragment(run_every=refresh)
def signals_panel():
    signals, _ = advisor.find_signals(live, include_unproven=show_unproven)
    for s in advisor.record_new(signals):
        if s["status"] == "TAKE":
            st.toast(f"New signal: {s['direction']} {s['symbol']} ({s['strategy']})", icon="🎯")
    st.caption(f"Last check {live.server_time():%H:%M:%S} server time · refreshes every {refresh}s")

    lab = advisor.load_lab()
    approved = [k for k, v in lab.items() if v.get("approved")]
    if not lab:
        st.warning("The strategy lab has not been run yet, so no strategy is approved for signals. "
                   "Run `python lab.py` once (takes a few minutes).")
    elif not approved:
        st.info("**No strategy has passed the lab test**, so there are no trade signals. "
                "This is deliberate: the advisor only signals setups with a proven backtest. "
                "Use the Market scanner for analysis, and check the Strategy lab tab.")
    else:
        st.caption("Approved strategies: " + ", ".join(approved))

    if not signals:
        st.success("**No trade right now.** No approved setup on any pair. Waiting is a position too.")
    for s in signals:
        signal_card(s)


with tabs[0]:
    signals_panel()


# ---------------- scanner ----------------
@st.cache_data(ttl=300, show_spinner="Scanning 28 pairs...")
def cached_scan(_live, bucket):
    return scanner.scan(_live)


with tabs[1]:
    st.subheader("What every pair is doing")
    sc = cached_scan(live, pd.Timestamp.now().floor("5min"))
    if sc.empty:
        st.info("No data.")
    else:
        top = sc.head(5)
        st.markdown("**Best conditions right now**")
        for r in top.itertuples():
            st.markdown(f"- **{r.pair}** - {r.state}: {r.advice}")
        avoid = sc[sc.state.isin(["Volatile", "Mixed"])].pair.tolist()
        if avoid:
            st.markdown(f"**Avoid for now:** {', '.join(avoid)}")
        st.dataframe(sc.drop(columns=["advice"]), hide_index=True, width="stretch")
        st.caption("Score: + for D1 and H4 trends agreeing and price near a key level; "
                   "- for volatility, upcoming news and mixed signals.")


# ---------------- lot calculator ----------------
with tabs[2]:
    st.subheader("Lot size for your own trade idea")
    c1, c2, c3 = st.columns(3)
    sym = c1.selectbox("Pair", live.symbols)
    side = c2.radio("Direction", ["BUY", "SELL"], horizontal=True)
    rp = c3.number_input("Risk %", 0.1, 5.0, risk_pct, 0.1)
    spec, tick = live.spec(sym), live.tick(sym)
    price = tick["ask"] if side == "BUY" else tick["bid"]
    step = spec["point"] * 10
    fmt = f"%.{spec['digits']}f"
    c1, c2, c3 = st.columns(3)
    entry = c1.number_input("Entry price", value=float(price), step=step, format=fmt)
    sl = c2.number_input("Stop-loss price", value=float(price - step * 20 if side == "BUY" else price + step * 20),
                         step=step, format=fmt)
    tp = c3.number_input("Take-profit price (optional, 0 = none)", value=0.0, step=step, format=fmt)
    d = 1 if side == "BUY" else -1
    if d * (entry - sl) <= 0:
        st.error("Stop-loss must be BELOW entry for a buy and ABOVE entry for a sell.")
    else:
        lots, money = risk.lot_size(acct.get("balance", 0), rp / 100, abs(entry - sl), spec)
        c = st.columns(4)
        c[0].metric("Lot size", lots)
        c[1].metric("Money at risk", f"{money:,.2f}")
        c[2].metric("Stop distance", f"{risk.pips(spec, abs(entry - sl)):.1f} pips")
        if tp and d * (tp - entry) > 0:
            c[3].metric("Reward : Risk", f"{abs(tp - entry) / abs(entry - sl):.2f} : 1")
        if lots == 0:
            st.warning("Below the broker's minimum lot - use a tighter stop or a bigger risk %.")
        positions = live.positions()
        for w in risk.trade_checks(live, positions, day, sym, d):
            st.warning(w)
        if news.block_mask(sym, [live.server_time().to_datetime64()], news.load_events())[0]:
            st.warning("High-impact news for this pair within the next hour.")


# ---------------- open trades ----------------
with tabs[3]:
    st.subheader("Your open trades")
    positions = live.positions()
    if not positions:
        st.info("No open trades.")
    else:
        df = pd.DataFrame(positions)
        df["side"] = df.direction.map({1: "BUY", -1: "SELL"})
        st.dataframe(df[["base", "side", "volume", "price_open", "sl", "tp", "profit"]]
                     .rename(columns={"base": "pair", "volume": "lots", "price_open": "entry"}),
                     hide_index=True, width="stretch")
        no_sl = df[df.sl == 0].base.tolist()
        if no_sl:
            st.error(f"No stop-loss on: {', '.join(no_sl)} - set one now.")
        exp = {k: v for k, v in risk.exposure(positions).items() if v}
        if exp:
            st.caption("Net currency exposure (+ long / - short): " +
                       ", ".join(f"{k} {v:+d}" for k, v in exp.items()))
        if len(positions) >= config.MAX_OPEN_TRADES:
            st.warning(f"You are at the max of {config.MAX_OPEN_TRADES} open trades.")


# ---------------- journal ----------------
with tabs[4]:
    st.subheader("Your closed trades (from MT5 history)")
    days = st.slider("Days", 7, 365, config.JOURNAL_DAYS)
    trades = journal.closed_trades(live, days)
    if trades.empty:
        st.info("No closed trades in this period.")
    else:
        s = journal.stats(trades)
        c = st.columns(6)
        c[0].metric("Trades", s["trades"])
        c[1].metric("Net P&L", f"{s['net_pnl']:,.2f}")
        c[2].metric("Win rate", f"{s['win_rate']}%")
        c[3].metric("Profit factor", s["profit_factor"])
        c[4].metric("Avg R", s["avg_r"] if s["avg_r"] is not None else "-")
        c[5].metric("Followed signals", f"{s['followed_signals']}/{s['trades']}")
        if s["no_stop_loss"]:
            st.warning(f"{s['no_stop_loss']} trade(s) had no stop-loss.")
        st.dataframe(trades, hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        c1.markdown("**By pair**")
        c1.dataframe(journal.breakdown(trades, "symbol"), width="stretch")
        c2.markdown("**Advisor signal vs your own idea**")
        c2.dataframe(journal.breakdown(trades.assign(source=trades.followed_signal.map(
            {True: "advisor signal", False: "own idea"})), "source"), width="stretch")


# ---------------- strategy lab ----------------
with tabs[5]:
    st.subheader("Which strategies are allowed to send signals")
    lab = lab_mod.load_results()
    if not lab:
        st.info("Not run yet. In the terminal: `python lab.py`")
    else:
        rows = []
        for k, v in lab.items():
            i, o = v.get("in_sample", {}), v.get("out_of_sample", {})
            rows.append({"strategy": k, "timeframe": v.get("timeframe", config.STRATEGY_TF.get(k)),
                         "status": "✅ approved" if v.get("approved") else "❌ rejected",
                         "PF 2021-23": i.get("profit_factor"), "PF 2024+": o.get("profit_factor"),
                         "trades": i.get("trades", 0) + o.get("trades", 0),
                         "win % 2024+": o.get("win_rate"), "max DD % 2024+": o.get("max_dd"),
                         "why rejected": "; ".join(v.get("reasons", [])), "tested": v.get("tested_at", "")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(f"Pass rule: profit factor ≥ {config.LAB_MIN_PF} in BOTH 2021-23 and 2024+, "
               f"≥ {config.LAB_MIN_TRADES} trades total, ≥ {config.LAB_MIN_OOS_TRADES} in 2024+. "
               "Re-run `python lab.py` monthly.")


# ---------------- news ----------------
with tabs[6]:
    st.subheader("High-impact news - next 7 days (server time)")
    if st.button("Update this week's calendar from Forex Factory"):
        try:
            news.update_from_forexfactory()
            st.success("Calendar updated.")
        except Exception as e:
            st.error(f"Update failed: {e}")
    ev = news.upcoming(news.load_events(), ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"],
                       live.server_time(), 24 * 7)
    if ev is None or ev.empty:
        st.info("No high-impact events loaded for the next 7 days. Click update above.")
    else:
        st.dataframe(ev, hide_index=True, width="stretch")
    st.caption(f"The advisor blocks new trades {config.NEWS_BLOCK_BEFORE_MIN} min before to "
               f"{config.NEWS_BLOCK_AFTER_MIN} min after these events for the affected pairs.")
