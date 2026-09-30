"""Instantané des marchés via Yahoo Finance (gratuit, sans clé) : dernier cours, variation, plus haut/bas de la veille.

Usage : python market_snapshot.py
"""

import json
import urllib.request

SYMBOLS = {
    "NQ=F": "Nasdaq 100 (futures)",
    "^NDX": "Nasdaq 100 (indice)",
    "ES=F": "S&P 500 (futures)",
    "^VIX": "VIX",
    "^TNX": "Taux US 10 ans (%)",
    "DX-Y.NYB": "Dollar (DXY)",
    "CL=F": "Pétrole WTI",
    "GC=F": "Or",
}


def quote(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=20))["chart"]["result"][0]
    meta, q = d["meta"], d["indicators"]["quote"][0]
    closes = [c for c in q["close"] if c is not None]
    prev = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose")
    last = meta["regularMarketPrice"]
    return {
        "dernier": round(last, 2),
        "var_%": round((last / prev - 1) * 100, 2) if prev else None,
        "cloture_veille": round(prev, 2) if prev else None,
        "haut_veille": round(q["high"][-2], 2) if len(q["high"]) >= 2 and q["high"][-2] else None,
        "bas_veille": round(q["low"][-2], 2) if len(q["low"]) >= 2 and q["low"][-2] else None,
    }


if __name__ == "__main__":
    for sym, name in SYMBOLS.items():
        try:
            print(f"{name:24} {json.dumps(quote(sym), ensure_ascii=False)}")
        except Exception as exc:
            print(f"{name:24} indisponible ({exc})")
