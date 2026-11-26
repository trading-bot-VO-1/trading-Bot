"""
Entry point.

  python run_backtest.py --download              # pull ~5 years of data from MT5, then backtest
  python run_backtest.py --timeframe H1 --strategies trend,breakout,meanrev
  python run_backtest.py                         # backtest using cached data in data/
  python run_backtest.py --walk-forward          # in-sample vs out-of-sample check
  python run_backtest.py --strategies trend,meanrev
  python run_backtest.py --symbols EURUSD,GBPJPY --start 2023-01-01
  python run_backtest.py --no-news --no-regime   # compare: what the filters add
"""
import argparse
import os
from datetime import datetime

import config
import mt5_data
import report
from backtest import Backtester


def main():
    ap = argparse.ArgumentParser(description="Forex bot backtest")
    ap.add_argument("--download", action="store_true", help="download fresh data from MT5 first")
    ap.add_argument("--symbols", help="comma-separated pairs (default: all in config.py)")
    ap.add_argument("--strategies", help="comma-separated: donchian,trend,breakout,meanrev (priority order)")
    ap.add_argument("--timeframe", help="M15, M30, H1, H4, D1 (default: config.TIMEFRAME)")
    ap.add_argument("--start", help="YYYY-MM-DD (default: config.START)")
    ap.add_argument("--end", help="YYYY-MM-DD (default: now)")
    ap.add_argument("--walk-forward", action="store_true",
                    help="run before and after config.WF_SPLIT separately and compare")
    ap.add_argument("--no-news", action="store_true", help="switch off the news filter")
    ap.add_argument("--no-regime", action="store_true", help="switch off the regime/volatility filter")
    ap.add_argument("--no-pause", action="store_true",
                    help="research mode: ignore the max-drawdown pause to see the full period")
    args = ap.parse_args()

    if args.timeframe:
        config.TIMEFRAME = args.timeframe.upper()
    if args.strategies:
        config.STRATEGIES = [s.strip().lower() for s in args.strategies.split(",")]
    if args.no_news:
        config.USE_NEWS_FILTER = False
    if args.no_regime:
        config.USE_REGIME_FILTER = False
    if args.no_pause:
        config.MAX_DRAWDOWN = 1.0

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else config.SYMBOLS
    start = datetime.fromisoformat(args.start) if args.start else config.START
    end = datetime.fromisoformat(args.end) if args.end else config.END

    missing = not os.path.exists(mt5_data.specs_path()) or not any(
        os.path.exists(mt5_data.csv_path(s, config.TIMEFRAME)) for s in symbols)
    if args.download or missing:
        print("Downloading from MT5...")
        mt5_data.download(symbols, config.TIMEFRAME, start, end)

    # load all cached history (indicators need warm-up); trading window applied in run()
    data, specs = mt5_data.load(symbols, config.TIMEFRAME)
    if not data:
        raise SystemExit("No data loaded. Check MT5 connection and symbols.")
    print(f"Pairs: {len(data)} | Timeframe: {config.TIMEFRAME} | Strategies: {', '.join(config.STRATEGIES)} | "
          f"News filter: {'on' if config.USE_NEWS_FILTER else 'off'} | "
          f"Regime filter: {'on' if config.USE_REGIME_FILTER else 'off'}")

    bt = Backtester(data, specs)
    run_dir = os.path.join(config.RESULTS_DIR, datetime.now().strftime("%Y%m%d_%H%M%S"))

    if args.walk_forward:
        split = config.WF_SPLIT
        ins = bt.run(start, split)
        print(report.save(ins, config.INITIAL_BALANCE, os.path.join(run_dir, "in_sample"),
                          f"IN-SAMPLE {start:%Y-%m-%d} -> {split:%Y-%m-%d}"))
        s_in = report.summary(ins, config.INITIAL_BALANCE)
        oos = bt.run(split, end)
        print(report.save(oos, config.INITIAL_BALANCE, os.path.join(run_dir, "out_of_sample"),
                          f"OUT-OF-SAMPLE {split:%Y-%m-%d} -> end"))
        s_out = report.summary(oos, config.INITIAL_BALANCE)
        cmp = report.compare({"in-sample": s_in, "out-of-sample": s_out})
        with open(os.path.join(run_dir, "walk_forward.txt"), "w") as f:
            f.write(cmp)
        print("\n=== WALK-FORWARD ===\n" + cmp)
        print("\nRule of thumb: out-of-sample profit factor should stay > 1.2 and "
              "drawdown should not be much worse than in-sample.")
    else:
        bt.run(start, end)
        print(report.save(bt, config.INITIAL_BALANCE, run_dir))

    print(f"\nSaved: {run_dir}")


if __name__ == "__main__":
    main()
