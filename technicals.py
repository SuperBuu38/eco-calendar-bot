"""Lecture technique chiffrée du Nasdaq 100 (contrats NQ), pour que Claude rédige des scénarios fiables.

Usage : python technicals.py        (affiche un résumé lisible)
        python technicals.py --json (même contenu en JSON)
"""

import json
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tasks import bars, close_time, session_levels, trading_day

TZ = ZoneInfo("Europe/Paris")


def ema(values, n):
    k, out = 2 / (n + 1), []
    for v in values:
        out.append(v if not out else v * k + out[-1] * (1 - k))
    return out


def rsi(closes, n=14):
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    return 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)


def atr(candles, n=14):
    trs = [max(h - l, abs(h - pc), abs(l - pc)) for (_, _, h, l, _), (_, _, _, _, pc) in zip(candles[1:], candles[:-1])]
    return sum(trs[-n:]) / min(n, len(trs)) if trs else 0


def trend(closes):
    e20, e50 = ema(closes, 20)[-1], ema(closes, 50)[-1]
    last = closes[-1]
    if last > e20 > e50:
        return "haussière", e20, e50
    if last < e20 < e50:
        return "baissière", e20, e50
    return "sans direction nette", e20, e50


def analyse():
    now = datetime.now(TZ)
    m15, _ = bars("NQ=F", "5d", "15m")
    h1, _ = bars("NQ=F", "1mo", "60m")
    d1, _ = bars("NQ=F", "6mo", "1d")
    last = m15[-1][4]
    today = now.date()
    lv = session_levels(m15, today)

    day = [c for c in m15 if c[0].date() == today]
    if day:
        lv["jour_h"], lv["jour_b"] = max(c[2] for c in day), min(c[3] for c in day)
    rth = [c for c in m15 if c[0].date() == today and (c[0].hour, c[0].minute) >= (15, 30)]
    if rth:  # VWAP approché de la séance US (prix typique, sans volume fiable sur les contrats continus)
        lv["vwap_seance"] = sum((c[2] + c[3] + c[4]) / 3 for c in rth) / len(rth)
    week_start = today - timedelta(days=today.weekday())
    week = [c for c in m15 if c[0].date() >= week_start]
    if week:
        lv["semaine_h"], lv["semaine_b"] = max(c[2] for c in week), min(c[3] for c in week)

    c15 = [c[4] for c in m15]
    c1h = [c[4] for c in h1]
    t15, e20_15, e50_15 = trend(c15)
    t1h, e20_1h, e50_1h = trend(c1h)
    daily_atr = atr(d1[:-1], 14) if len(d1) > 15 else 0
    day_range = (lv["jour_h"] - lv["jour_b"]) if day else 0

    above = sorted((v, k) for k, v in lv.items() if v > last)
    below = sorted(((v, k) for k, v in lv.items() if v < last), reverse=True)
    step = 250  # chiffres ronds du Nasdaq 100, souvent respectés
    rounds = {"rond_dessus": (int(last // step) + 1) * step, "rond_dessous": int(last // step) * step}

    return {
        "heure_paris": now.strftime("%d/%m %H:%M"),
        "cours": round(last, 2),
        "niveaux": {k: round(v, 2) for k, v in lv.items()},
        "resistances_proches": [{"niveau": k, "prix": round(v, 2), "ecart_pts": round(v - last, 1)} for v, k in above[:3]],
        "supports_proches": [{"niveau": k, "prix": round(v, 2), "ecart_pts": round(last - v, 1)} for v, k in below[:3]],
        "chiffres_ronds": rounds,
        "tendance_15min": {"etat": t15, "ema20": round(e20_15, 2), "ema50": round(e50_15, 2)},
        "tendance_1h": {"etat": t1h, "ema20": round(e20_1h, 2), "ema50": round(e50_1h, 2)},
        "rsi_15min": round(rsi(c15), 1),
        "rsi_1h": round(rsi(c1h), 1),
        "atr_15min_pts": round(atr(m15), 1),
        "amplitude_habituelle_jour_pts": round(daily_atr, 1),
        "amplitude_du_jour_pts": round(day_range, 1),
        "amplitude_consommee_pct": round(day_range / daily_atr * 100) if daily_atr else None,
        "seance_us_ouverte": trading_day(today) and (15, 30) <= (now.hour, now.minute) < close_time(today),
    }


if __name__ == "__main__":
    a = analyse()
    if "--json" in sys.argv:
        print(json.dumps(a, ensure_ascii=False, indent=1))
        sys.exit()
    print(f"Nasdaq 100 (NQ) {a['cours']} à {a['heure_paris']} (heure de Paris) · séance US ouverte : {a['seance_us_ouverte']}")
    print("Résistances proches : " + ", ".join(f"{r['niveau']} {r['prix']} (+{r['ecart_pts']} pts)" for r in a["resistances_proches"]))
    print("Supports proches : " + ", ".join(f"{s['niveau']} {s['prix']} (-{s['ecart_pts']} pts)" for s in a["supports_proches"]))
    print(f"Chiffres ronds : {a['chiffres_ronds']}")
    print(f"Tendance 15 min : {a['tendance_15min']} · 1 h : {a['tendance_1h']}")
    print(f"RSI 15 min {a['rsi_15min']} · RSI 1 h {a['rsi_1h']} (>70 suracheté, <30 survendu)")
    print(f"ATR 15 min {a['atr_15min_pts']} pts · amplitude habituelle/jour {a['amplitude_habituelle_jour_pts']} pts · "
          f"amplitude du jour {a['amplitude_du_jour_pts']} pts ({a['amplitude_consommee_pct']} % de l'habituel)")
    print("Tous les niveaux : " + json.dumps(a["niveaux"], ensure_ascii=False))
