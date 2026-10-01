"""Évolution par quart d'heure des dernières heures (heure de Paris) pour repérer ce qui a bougé EN MÊME TEMPS
que le Nasdaq : pétrole, taux, dollar, Europe, VIX, or, poids lourds de la tech.

Usage : python intraday.py [heures=4]
"""

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
SYMBOLS = [("NQ=F", "Nasdaq 100 fut."), ("ES=F", "S&P 500 fut."), ("CL=F", "Pétrole WTI"), ("^TNX", "Taux US 10 ans"),
           ("DX-Y.NYB", "Dollar DXY"), ("^STOXX50E", "EuroStoxx 50"), ("^N225", "Nikkei"), ("GC=F", "Or"),
           ("^VIX", "VIX"), ("NVDA", "Nvidia"), ("MU", "Micron")]


def series(sym, hours):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2d&interval=15m&includePrePost=true"
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
    r = d["chart"]["result"][0]
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [(datetime.fromtimestamp(t, timezone.utc), c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"])
            if c is not None and datetime.fromtimestamp(t, timezone.utc) >= since]


if __name__ == "__main__":
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 4
    print(f"Variations par quart d'heure sur {hours:g} h (heure de Paris). Une grosse variation au même moment que le Nasdaq = piste.")
    for sym, name in SYMBOLS:
        try:
            pts = series(sym, hours)
            if len(pts) < 2:
                print(f"{name:16} pas de cotation récente")
                continue
            first, last = pts[0][1], pts[-1][1]
            steps = []
            for (t0, a), (t1, b) in zip(pts, pts[1:]):
                ch = (b / a - 1) * 100
                if abs(ch) >= 0.25:
                    steps.append(f"{t1.astimezone(TZ):%H:%M} {ch:+.2f}%")
            print(f"{name:16} {first:.2f} → {last:.2f} ({(last / first - 1) * 100:+.2f}%) | gros pas : {', '.join(steps) or 'aucun'}")
        except Exception as exc:
            print(f"{name:16} indisponible ({exc})")
