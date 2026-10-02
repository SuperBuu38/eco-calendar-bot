"""Carte des niveaux et analyse multi-unités de temps du Nasdaq 100 (contrats NQ).

Usage : python levels.py           (analyse lisible : niveaux + jour / 4 h / 1 h / 15 min)
        python levels.py --map     (génère out/carte-niveaux.png)
        python levels.py --weekly  (génère out/carte-semaine.png, bougies journalières ~3 mois)
"""

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tasks import bars, chart_png, num, session_levels, trading_day
from technicals import atr, ema, rsi

TZ = ZoneInfo("Europe/Paris")
ROUND = 500  # chiffres ronds majeurs du Nasdaq 100


def aggregate(candles, hours):
    """Regroupe des bougies 1 h en bougies de `hours` heures (calées sur minuit Paris)."""
    out, cur, key = [], None, None
    for dt, o, h, l, c in candles:
        k = (dt.date(), dt.hour // hours)
        if k != key:
            if cur:
                out.append(tuple(cur))
            key, cur = k, [dt.replace(hour=dt.hour // hours * hours, minute=0), o, h, l, c]
        else:
            cur[2], cur[3], cur[4] = max(cur[2], h), min(cur[3], l), c
    if cur:
        out.append(tuple(cur))
    return out


def structure(candles, n=6):
    """Plus hauts / plus bas croissants ou décroissants sur les 2 derniers blocs de n bougies."""
    if len(candles) < 2 * n:
        return "indéterminée"
    a, b = candles[-2 * n:-n], candles[-n:]
    hh, hl = max(c[2] for c in b) > max(c[2] for c in a), min(c[3] for c in b) > min(c[3] for c in a)
    lh, ll = max(c[2] for c in b) < max(c[2] for c in a), min(c[3] for c in b) < min(c[3] for c in a)
    if hh and hl:
        return "haussière (plus hauts et plus bas croissants)"
    if lh and ll:
        return "baissière (plus hauts et plus bas décroissants)"
    return "en range / indécise"


def tf_summary(name, candles):
    closes = [c[4] for c in candles]
    e20, e50 = ema(closes, 20)[-1], ema(closes, 50)[-1]
    last = closes[-1]
    pos = ("au-dessus" if last > e20 else "en dessous") + " de la MM20, " + ("au-dessus" if last > e50 else "en dessous") + " de la MM50"
    slope = "MM20 montante" if ema(closes, 20)[-1] > ema(closes, 20)[-4] else "MM20 descendante"
    return (f"{name:7} : {pos} ({num(e20)} / {num(e50)}), {slope} · structure {structure(candles)} · "
            f"RSI {rsi(closes):.0f} · ATR {num(atr(candles), 0)} pts")


def compute():
    now = datetime.now(TZ)
    d1, _ = bars("NQ=F", "6mo", "1d")
    h1, _ = bars("NQ=F", "1mo", "60m")
    m15, _ = bars("NQ=F", "5d", "15m")
    last = m15[-1][4]
    today = now.date()
    lv = {}
    sl = session_levels(m15, today if now.hour < 22 else today + timedelta(days=1))
    names = {"veille_h": "Veille H", "veille_b": "Veille B", "veille_c": "Clôture veille", "nuit_h": "Nuit H", "nuit_b": "Nuit B"}
    for k, v in sl.items():
        lv[names[k]] = v
    # semaine et mois précédents (bougies journalières des contrats)
    monday = today - timedelta(days=today.weekday())
    prev_week = [c for c in d1 if monday - timedelta(days=7) <= c[0].date() < monday]
    if prev_week:
        lv["Semaine préc. H"], lv["Semaine préc. B"] = max(c[2] for c in prev_week), min(c[3] for c in prev_week)
    first_month = today.replace(day=1)
    prev_month_start = (first_month - timedelta(days=1)).replace(day=1)
    prev_month = [c for c in d1 if prev_month_start <= c[0].date() < first_month]
    if prev_month:
        lv["Mois préc. H"], lv["Mois préc. B"] = max(c[2] for c in prev_month), min(c[3] for c in prev_month)
    week_bars = [c for c in h1 if c[0].date() >= monday - timedelta(days=1)]
    if week_bars:
        lv["Ouverture semaine"] = week_bars[0][1]
    lv["Rond haut"] = (int(last // ROUND) + 1) * ROUND
    lv["Rond bas"] = int(last // ROUND) * ROUND
    # niveaux identiques (à 5 pts près) fusionnés : « Semaine/Mois préc. H »
    merged = {}
    for k, v in sorted(lv.items(), key=lambda kv: kv[1]):
        twin = next((mk for mk, mv in merged.items() if abs(mv - v) <= 5), None)
        if twin:
            short = lambda n: n.replace("Semaine préc.", "Sem.").replace("Mois préc.", "Mois")
            merged[f"{short(twin)} = {short(k)}"] = merged.pop(twin)
        else:
            merged[k] = v
    lv = merged
    daily_atr = atr(d1[:-1], 14)
    return {"now": now, "last": last, "levels": lv, "atr_jour": daily_atr, "d1": d1,
            "h4": aggregate(h1, 4), "h1": h1, "m15": m15}


def print_analysis(a):
    last = a["last"]
    print(f"Nasdaq 100 (NQ) {num(last)} · {a['now']:%d/%m %H:%M} (heure de Paris)")
    print(f"Amplitude habituelle (ATR 14 jours) : {num(a['atr_jour'])} pts "
          f"→ zone probable de la prochaine séance ≈ {num(last - a['atr_jour'] / 2)} – {num(last + a['atr_jour'] / 2)}")
    above = sorted((v, k) for k, v in a["levels"].items() if v > last)
    below = sorted(((v, k) for k, v in a["levels"].items() if v <= last), reverse=True)
    print("Résistances : " + " · ".join(f"{k} {num(v)} (+{num(v - last)})" for v, k in above[:5]))
    print("Supports    : " + " · ".join(f"{k} {num(v)} (-{num(last - v)})" for v, k in below[:5]))
    print("Multi-unités de temps :")
    for name, c in (("Jour", a["d1"]), ("4 h", a["h4"]), ("1 h", a["h1"]), ("15 min", a["m15"])):
        print("  " + tf_summary(name, c))


COLORS = {"Veille": "#f2b94b", "Clôture": "#94a3b8", "Nuit": "#38bdf8", "Semaine": "#a78bfa",
          "Mois": "#f472b6", "Ouverture": "#22c55e", "Rond": "#64748b"}


def level_lines(levels, candles, margin):
    lo, hi = min(c[3] for c in candles) - margin, max(c[2] for c in candles) + margin
    out, hidden = [], []
    for k, v in levels.items():
        col = next((c for p, c in COLORS.items() if k.startswith(p)), "#94a3b8")
        (out if lo <= v <= hi else hidden).append((k, v, col))
    return out, hidden


def make_map(a, weekly=False):
    if weekly:
        candles = [c for c in a["d1"] if c[0].date() >= a["now"].date() - timedelta(days=95)]
        title = f"Nasdaq 100 · carte de la semaine · bougies journalières · {a['now']:%d/%m}"
        name = "carte-semaine.png"
    else:
        start = a["now"] - timedelta(days=6)
        candles = [c for c in a["h1"] if c[0] >= start]
        title = f"Nasdaq 100 · carte des niveaux · bougies 1 h · {a['now']:%d/%m %H:%M}"
        name = "carte-niveaux.png"
    levels = a["levels"]
    if weekly:  # sur la carte hebdo, seulement les niveaux de fond
        levels = {k: v for k, v in levels.items() if k.startswith(("Semaine", "Mois", "Rond", "Ouverture"))}
    lines, hidden = level_lines(levels, candles, a["atr_jour"] * (2 if weekly else 0.6))
    return chart_png(candles, lines, title, name), hidden


if __name__ == "__main__":
    data = compute()
    if "--map" in sys.argv or "--weekly" in sys.argv:
        img, hidden = make_map(data, weekly="--weekly" in sys.argv)
        print(f"Carte : {img}")
        if hidden:
            print("Hors graphique : " + ", ".join(f"{k} {num(v)}" for k, v, _ in hidden))
    else:
        print_analysis(data)
