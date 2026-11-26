"""
Strategy lab - the gatekeeper for trade signals.

Walk-forward tests every strategy in config.LAB_STRATEGIES on its own timeframe
(config.STRATEGY_TF), with real spread, on all pairs:
  in-sample      config.START    -> config.WF_SPLIT
  out-of-sample  config.WF_SPLIT -> now

A strategy is APPROVED only if:
  profit factor >= LAB_MIN_PF in BOTH periods,
  total trades >= LAB_MIN_TRADES and out-of-sample trades >= LAB_MIN_OOS_TRADES.

Results go to data/lab_results.json. The advisor reads that file: only approved
strategies produce "TAKE" signals.

  python lab.py                 # test all (downloads missing data from MT5)
  python lab.py --download      # refresh data first
  python lab.py --only mtf,sr_bounce
"""
import argparse
import json
import os
from datetime import datetime

import pandas as pd

import config
import mt5_data
import report
from backtest import Backtester


def _metrics(bt):
    s = report.summary(bt, config.INITIAL_BALANCE)
    pf = s.get("Profit factor", 0.0)
    return {
        "trades": int(s.get("Trades", 0)),
        "profit_factor": float(pf) if pf != float("inf") else 99.0,
        "win_rate": float(s.get("Win rate %", 0.0)),
        "avg_r": float(s.get("Avg R per trade", 0.0)),
        "max_dd": float(s.get("Max drawdown %", 0.0)),
        "net_return": float(s.get("Net return %", 0.0)),
    }


def _pair_stats(trades):
    out = {}
    if trades.empty:
        return out
    for sym, g in trades.groupby("symbol"):
        wins, losses = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum()
        out[sym] = {
            "trades": int(len(g)),
            "win_rate": round(float((g.pnl > 0).mean() * 100), 1),
            "profit_factor": round(float(wins / losses), 2) if losses > 0 else 99.0,
            "avg_r": round(float(g.r_multiple.mean()), 3),
        }
    return out


def test_strategy(name, download=False):
    tf = config.STRATEGY_TF[name]
    config.TIMEFRAME = tf
    config.STRATEGIES = [name]
    config.MAX_DRAWDOWN = 1.0            # research mode: see the full period

    have = os.path.exists(mt5_data.specs_path()) and any(
        os.path.exists(mt5_data.csv_path(s, tf)) for s in config.SYMBOLS)
    if download or not have:
        print(f"  downloading {tf} data from MT5...")
        mt5_data.download(config.SYMBOLS, tf, config.START, config.END)

    data, specs = mt5_data.load(config.SYMBOLS, tf)
    bt = Backtester(data, specs)

    ins = bt.run(config.START, config.WF_SPLIT)
    m_in, t_in = _metrics(ins), ins.trades_df.copy()
    oos = bt.run(config.WF_SPLIT, config.END)
    m_out, t_out = _metrics(oos), oos.trades_df.copy()

    total = m_in["trades"] + m_out["trades"]
    reasons = []
    if m_in["profit_factor"] < config.LAB_MIN_PF:
        reasons.append(f"in-sample PF {m_in['profit_factor']:.2f} < {config.LAB_MIN_PF}")
    if m_out["profit_factor"] < config.LAB_MIN_PF:
        reasons.append(f"out-of-sample PF {m_out['profit_factor']:.2f} < {config.LAB_MIN_PF}")
    if total < config.LAB_MIN_TRADES:
        reasons.append(f"only {total} trades (< {config.LAB_MIN_TRADES})")
    if m_out["trades"] < config.LAB_MIN_OOS_TRADES:
        reasons.append(f"only {m_out['trades']} out-of-sample trades (< {config.LAB_MIN_OOS_TRADES})")

    return {
        "timeframe": tf,
        "approved": not reasons,
        "reasons": reasons,
        "in_sample": m_in,
        "out_of_sample": m_out,
        "pairs": _pair_stats(pd.concat([t_in, t_out], ignore_index=True)),
        "tested_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def load_results():
    if not os.path.exists(config.LAB_RESULTS):
        return {}
    with open(config.LAB_RESULTS) as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="Strategy lab - approve strategies for signals")
    ap.add_argument("--download", action="store_true", help="refresh MT5 data first")
    ap.add_argument("--only", help="comma-separated strategy names")
    args = ap.parse_args()

    names = [s.strip() for s in args.only.split(",")] if args.only else config.LAB_STRATEGIES
    results = load_results()
    for name in names:
        print(f"\nTesting {name} ({config.STRATEGY_TF[name]}) ...")
        results[name] = test_strategy(name, args.download)
        r = results[name]
        verdict = "APPROVED" if r["approved"] else "REJECTED - " + "; ".join(r["reasons"])
        print(f"  in-sample PF {r['in_sample']['profit_factor']:.2f} ({r['in_sample']['trades']} trades) | "
              f"out-of-sample PF {r['out_of_sample']['profit_factor']:.2f} ({r['out_of_sample']['trades']} trades)")
        print(f"  -> {verdict}")

    os.makedirs(os.path.dirname(config.LAB_RESULTS) or ".", exist_ok=True)
    with open(config.LAB_RESULTS, "w") as f:
        json.dump(results, f, indent=2)

    rows = [{"strategy": k, "tf": v["timeframe"], "approved": v["approved"],
             "PF in": v["in_sample"]["profit_factor"], "PF out": v["out_of_sample"]["profit_factor"],
             "trades": v["in_sample"]["trades"] + v["out_of_sample"]["trades"]}
            for k, v in results.items()]
    print("\n=== STRATEGY LAB ===")
    print(pd.DataFrame(rows).to_string(index=False))
    approved = [r["strategy"] for r in rows if r["approved"]]
    print("\nApproved for signals:", ", ".join(approved) if approved else
          "NONE - the advisor will show market analysis but no trade signals.")
    print(f"Saved: {config.LAB_RESULTS}")


if __name__ == "__main__":
    main()
