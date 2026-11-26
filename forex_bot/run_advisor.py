"""
Terminal advisor + alerts (use this if you don't want the dashboard open).

  python run_advisor.py              # check every REFRESH_SECONDS, print + Telegram new signals
  python run_advisor.py --once       # check once and exit
  python run_advisor.py --unproven   # also show STUDY ONLY signals

Never places trades.
"""
import argparse
import time

import alerts
import advisor
import config
from live import Live


def check(live, unproven):
    signals, day = advisor.find_signals(live, unproven)
    new = advisor.record_new(signals)
    stamp = live.server_time().strftime("%Y-%m-%d %H:%M")
    lock = "LOCKED - stop trading today" if day["locked"] else f"room left ${day['loss_room']}"
    print(f"[{stamp}] today {day['pnl_today']:+.2f} ({day['pnl_today_pct']:+.2f}%) | {lock} | "
          f"{len(signals)} active signal(s), {len(new)} new")
    for s in new:
        text = advisor.format_signal(s)
        print("\n" + text + "\n")
        if s["status"] == "TAKE":
            alerts.telegram(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--unproven", action="store_true")
    a = ap.parse_args()

    live = Live()
    lab = advisor.load_lab()
    ok = [k for k, v in lab.items() if v.get("approved")]
    print("Approved strategies:", ", ".join(ok) if ok else "none (run: python lab.py)")
    print("Telegram alerts:", "on" if alerts.enabled() else "off")
    while True:
        check(live, a.unproven)
        if a.once:
            break
        time.sleep(config.REFRESH_SECONDS)


if __name__ == "__main__":
    main()
