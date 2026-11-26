"""Optional Telegram alerts. Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in config.py."""
import json
import urllib.parse
import urllib.request

import config


def enabled():
    return bool(config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID)


def telegram(text):
    if not enabled():
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": config.TELEGRAM_CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:  # never let an alert failure stop the advisor
        print(f"Telegram alert failed: {e}")
        return False
