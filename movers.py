"""Détecteur de gros mouvement du Nasdaq 100 (contrats à terme NQ), lancé toutes les 15 min par GitHub Actions.

Déclencheurs :
  - mouvement rapide : variation d'au moins FAST_PCT % sur 1 heure (une alerte par sens toutes les 2 h au plus) ;
  - paliers depuis la clôture de la veille : LEVELS (une alerte par palier et par sens et par séance).
Quand ça se déclenche : alerte immédiate dans #alertes, puis (si configuré) réveil de la routine Claude
qui cherche pourquoi et poste l'explication.

Test local : DRY_RUN=1 FAST_PCT=0.05 python movers.py
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
SYMBOL = "NQ=F"
FAST_PCT = float(os.getenv("FAST_PCT", "0.7"))
LEVELS = [float(x) for x in os.getenv("LEVELS", "1.2,2,3").split(",")]
COOLDOWN = timedelta(hours=2)
AMPLIFY_PCT = float(os.getenv("AMPLIFY_PCT", "0.5"))
STATE_FILE = Path(os.getenv("STATE_DIR", "state")) / "movers.json"
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
WEBHOOK = os.getenv("WEBHOOK_ALERTES", "")
FIRE_URL = os.getenv("ROUTINE_FIRE_URL", "")
FIRE_TOKEN = os.getenv("ROUTINE_FIRE_TOKEN", "")


def fr(x, d=2):
    return f"{x:+.{d}f}".replace(".", ",")


def num(x):
    return f"{x:,.0f}".replace(",", " ")


def fetch():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}?range=1d&interval=5m&includePrePost=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.load(urllib.request.urlopen(req, timeout=20))["chart"]["result"][0]
    meta = d["meta"]
    bars = [(datetime.fromtimestamp(t, timezone.utc), c)
            for t, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]) if c is not None]
    return meta, bars


def post(content, image=None):
    if DRY_RUN or not WEBHOOK:
        print("[Discord]", content, "| image :", image)
        return
    from tasks import post as tpost
    tpost(WEBHOOK, content, image)


def fire_routine(text):
    if DRY_RUN or not (FIRE_URL and FIRE_TOKEN):
        print("[Routine non déclenchée]", text)
        return False
    req = urllib.request.Request(FIRE_URL, data=json.dumps({"text": text}).encode(), headers={
        "Authorization": f"Bearer {FIRE_TOKEN}", "anthropic-beta": "experimental-cc-routine-2026-04-01",
        "anthropic-version": "2023-06-01", "Content-Type": "application/json", "User-Agent": "eco-calendar-bot/2.0"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except Exception as exc:
        print(f"Routine non déclenchée ({exc})")
        return False


def main():
    meta, bars = fetch()
    now = datetime.now(timezone.utc)
    last_t, last = bars[-1]
    if now - last_t > timedelta(minutes=30):
        print("Marché fermé (pas de cotation récente).")
        return
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    ref = [c for t, c in bars if t <= last_t - timedelta(minutes=60)]
    p60 = ref[-1] if ref else bars[0][1]
    d60 = (last / p60 - 1) * 100
    dsess = (last / prev_close - 1) * 100 if prev_close else 0.0
    session = (last_t - timedelta(hours=22)).date().isoformat()  # une « séance » de NQ démarre vers 0h Paris
    print(f"NQ {last:.2f} | 1h {d60:+.2f}% | depuis la clôture {dsess:+.2f}%")

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    reasons = []

    if abs(d60) >= FAST_PCT:
        key = f"fast:{'up' if d60 > 0 else 'down'}"
        last_alert = state.get(key)
        if not last_alert or now - datetime.fromisoformat(last_alert) >= COOLDOWN:
            state[key] = now.isoformat()
            reasons.append(f"{fr(d60)} % en 1 heure ({num(p60)} → {num(last)})")

    for lvl in LEVELS:
        if abs(dsess) >= lvl:
            key = f"lvl:{session}:{'up' if dsess > 0 else 'down'}:{lvl}"
            if key not in state:
                state[key] = now.isoformat()
                fast_dir = (d60 > 0) if abs(d60) >= FAST_PCT else None
                same_dir = fast_dir is None or fast_dir == (dsess > 0)
                if same_dir and (not reasons or lvl == max(l for l in LEVELS if abs(dsess) >= l)):
                    reasons.append(f"{fr(dsess)} % depuis la clôture d'hier (palier ±{str(lvl).replace('.', ',')} %)")

    up = (d60 if abs(d60) >= FAST_PCT else dsess) > 0
    # Anti-bruit : une seule alerte par mouvement. Dans le même sens et dans l'heure qui suit,
    # on ne réalerte que si le mouvement s'est amplifié d'au moins AMPLIFY_PCT depuis la dernière alerte.
    if reasons:
        side = "up" if up else "down"
        prev = state.get(f"last:{side}")
        if prev:
            p_t, p_price = prev.split("|")
            if now - datetime.fromisoformat(p_t) < timedelta(hours=1) and \
                    abs(last / float(p_price) - 1) * 100 < AMPLIFY_PCT:
                print(f"Mouvement déjà signalé à {p_t[11:16]} UTC (pas d'amplification suffisante) : pas de nouvelle alerte.")
                reasons = []
        if reasons:
            state[f"last:{side}"] = f"{now.isoformat()}|{last}"

    # ménage : on garde 3 jours d'historique
    cutoff = (now - timedelta(days=3)).isoformat()
    state = {k: v for k, v in state.items() if v >= cutoff}
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")

    if not reasons:
        print("Pas de mouvement notable.")
        return
    paris = last_t.astimezone(TZ)
    icon = "🚀" if up else "🔻"
    head = f"{icon} **Nasdaq 100 {'en forte hausse' if up else 'en forte baisse'}** · {paris:%H:%M}"
    body = "\n".join(f"• {r}" for r in reasons)
    ctx = f"Cours {num(last)} · {fr(dsess)} % depuis la clôture d'hier ({num(prev_close)})"
    fired = fire_routine(
        f"Mouvement détecté sur les contrats à terme Nasdaq 100 (NQ) à {paris:%H:%M} heure de Paris, le {paris:%d/%m/%Y}.\n"
        f"Dernier cours : {last:.2f}. Il y a 1 heure : {p60:.2f} ({d60:+.2f} %). "
        f"Clôture de la veille : {prev_close:.2f} ({dsess:+.2f} %).\nDéclencheurs : " + " ; ".join(reasons))
    tail = "\n🔎 Analyse et scénarios en cours…" if fired else ""
    image = None
    try:  # graphique des 8 dernières heures avec les niveaux clés
        from tasks import bars as tbars, chart_png, session_levels
        m15, _ = tbars("NQ=F", "5d", "15m")
        lv = session_levels(m15, paris.date())
        levels = [(n, lv[k], col) for n, k, col in [("Veille H", "veille_h", "#f2b94b"), ("Veille B", "veille_b", "#f2b94b"),
                                                     ("Clôture", "veille_c", "#94a3b8"), ("Nuit H", "nuit_h", "#38bdf8"),
                                                     ("Nuit B", "nuit_b", "#38bdf8")] if k in lv]
        recent = [c for c in m15 if c[0] >= paris - timedelta(hours=8)]
        image = chart_png(recent, levels, f"Nasdaq 100 · bougies 15 min · {paris:%d/%m %H:%M}", "alerte.png")
    except Exception as exc:
        print(f"Graphique indisponible ({exc})")
    post(f"{head}\n{body}\n{ctx}{tail}", image)


if __name__ == "__main__":
    sys.exit(main())
