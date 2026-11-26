"""
Turns a finished backtest into numbers, CSVs and an equity chart.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _profit_factor(pnl):
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return float("inf") if losses == 0 else wins / losses


def summary(bt, initial_balance):
    tr, eq = bt.trades_df, bt.equity
    out = {"Trades": len(tr)}
    if len(tr) == 0 or len(eq) == 0:
        return out

    final = bt.balance
    years = max((eq.time.iloc[-1] - eq.time.iloc[0]).days / 365.25, 1e-9)
    dd = (eq.equity / eq.equity.cummax() - 1).min()
    daily = eq.set_index("time").equity.resample("D").last().dropna().pct_change().dropna()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0.0

    out.update({
        "Period": f"{eq.time.iloc[0]:%Y-%m-%d} -> {eq.time.iloc[-1]:%Y-%m-%d}",
        "Start balance": round(initial_balance, 2),
        "End balance": round(final, 2),
        "Net return %": round((final / initial_balance - 1) * 100, 2),
        "CAGR %": round(((final / initial_balance) ** (1 / years) - 1) * 100, 2),
        "Max drawdown %": round(dd * 100, 2),
        "Win rate %": round((tr.pnl > 0).mean() * 100, 2),
        "Profit factor": round(_profit_factor(tr.pnl), 2),
        "Avg R per trade": round(tr.r_multiple.mean(), 3),
        "Sharpe (daily)": round(sharpe, 2),
        "Avg trades / month": round(len(tr) / (years * 12), 1),
        "Signals skipped (news)": getattr(bt, "news_skips", 0),
        "Exit reasons": tr.reason.value_counts().to_dict(),
    })
    return out


def _group_table(tr, key):
    g = tr.groupby(key)
    table = pd.DataFrame({
        "trades": g.size(),
        "win_rate_%": g.pnl.apply(lambda p: round((p > 0).mean() * 100, 1)),
        "net_pnl": g.pnl.sum().round(2),
        "profit_factor": g.pnl.apply(lambda p: round(_profit_factor(p), 2)),
        "avg_R": g.r_multiple.mean().round(3),
    })
    return table


def per_symbol(bt):
    tr = bt.trades_df
    return _group_table(tr, "symbol").sort_values("net_pnl", ascending=False) if len(tr) else pd.DataFrame()


def per_strategy(bt):
    tr = bt.trades_df
    return _group_table(tr, "strategy").sort_values("net_pnl", ascending=False) if len(tr) else pd.DataFrame()


def per_year(bt):
    tr = bt.trades_df
    if not len(tr):
        return pd.DataFrame()
    tr = tr.assign(year=pd.to_datetime(tr.exit_time).dt.year)
    return _group_table(tr, "year")


def save(bt, initial_balance, out_dir, title="PORTFOLIO SUMMARY"):
    os.makedirs(out_dir, exist_ok=True)
    s = summary(bt, initial_balance)
    sym, strat, yr = per_symbol(bt), per_strategy(bt), per_year(bt)

    bt.trades_df.to_csv(os.path.join(out_dir, "trades.csv"), index=False)
    bt.equity.to_csv(os.path.join(out_dir, "equity.csv"), index=False)
    sym.to_csv(os.path.join(out_dir, "per_symbol.csv"))
    strat.to_csv(os.path.join(out_dir, "per_strategy.csv"))
    yr.to_csv(os.path.join(out_dir, "per_year.csv"))

    lines = [f"=== {title} ==="]
    lines += [f"{k:<24} {v}" for k, v in s.items()]
    if bt.events:
        daily = [e for e in bt.events if "Daily" in e[1]]
        lines.append(f"{'Daily-limit days':<24} {len(daily)}")
        for ts, msg in bt.events:
            if "DRAWDOWN" in msg:
                lines.append(f"!! {ts:%Y-%m-%d %H:%M}  {msg}")
    for name, tbl in (("PER STRATEGY", strat), ("PER YEAR", yr), ("PER PAIR", sym)):
        lines += ["", f"=== {name} ===", tbl.to_string() if len(tbl) else "(no trades)"]
    text = "\n".join(lines)
    with open(os.path.join(out_dir, "summary.txt"), "w") as f:
        f.write(text)

    if len(bt.equity):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True,
                                       gridspec_kw={"height_ratios": [3, 1]})
        ax1.plot(bt.equity.time, bt.equity.equity, lw=1, label="Equity")
        ax1.plot(bt.equity.time, bt.equity.balance, lw=1, alpha=0.6, label="Balance")
        ax1.set_title(title.title())
        ax1.legend()
        ax1.grid(alpha=0.3)
        dd = (bt.equity.equity / bt.equity.equity.cummax() - 1) * 100
        ax2.fill_between(bt.equity.time, dd, 0, color="tab:red", alpha=0.4)
        ax2.set_ylabel("Drawdown %")
        ax2.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, "equity.png"), dpi=120)
        plt.close(fig)

    return text


KEY_METRICS = ["Trades", "Net return %", "CAGR %", "Max drawdown %", "Win rate %",
               "Profit factor", "Avg R per trade", "Sharpe (daily)"]


def compare(results):
    """results: {label: summary-dict} -> side-by-side text table."""
    df = pd.DataFrame({k: {m: v.get(m, "-") for m in KEY_METRICS} for k, v in results.items()})
    return df.to_string()
