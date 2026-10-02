"""Cours d'une action (séance, après Bourse, avant Bourse) via Yahoo Finance.  Usage : python quote.py NVDA"""

import json
import sys
import urllib.request

for sym in sys.argv[1:]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2d&interval=5m&includePrePost=true"
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
        m = r["chart"]["result"][0]["meta"]
        closes = [c for c in r["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
        reg, prev, last = m.get("regularMarketPrice"), m.get("chartPreviousClose"), closes[-1] if closes else None
        print(f"{sym} : clôture/séance {reg} · veille {prev} · dernier cours (y compris hors séance) {last}"
              + (f" · {((last / reg) - 1) * 100:+.2f} % vs clôture" if last and reg else ""))
    except Exception as exc:
        print(f"{sym} : indisponible ({exc})")
