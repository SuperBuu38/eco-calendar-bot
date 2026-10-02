"""Agenda intraday du Nasdaq, appelé toutes les 5 min par la boucle du détecteur (movers.yml).

Chaque tâche ne part qu'une fois, et seulement quand elle a lieu d'être :
  - 15h00        brief d'avant-ouverture US (niveaux clés + contexte + graphique)      → #nasdaq
  - à la minute  chiffres US à fort impact dès leur publication (groupés par heure)    → #alertes
                 + analyse Claude du communiqué si c'est une décision de la Fed
  - 14h00/22h20  résultats des poids lourds du Nasdaq publiés (résumé par Claude)      → #nasdaq
  - 22h30        bilan de la séance                                                    → #nasdaq

Test local : DRY_RUN=1 NOW=2026-10-02T15:05 python tasks.py
"""

import json
import os
import re
import sys
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import bot
import earnings
from special_dates import EARLY_CLOSE, HOLIDAYS
from translations import translate

TZ = ZoneInfo("Europe/Paris")
STATE_FILE = Path(os.getenv("STATE_DIR", "state")) / "tasks.json"
OUT = Path(os.getenv("OUT_DIR", "out"))
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
WEBHOOK_NASDAQ = os.getenv("WEBHOOK_NASDAQ", "")
WEBHOOK_ALERTES = os.getenv("WEBHOOK_ALERTES", "")
FIRE_URL = os.getenv("ROUTINE_FIRE_URL", "")
FIRE_TOKEN = os.getenv("ROUTINE_FIRE_TOKEN", "")
UA = {"User-Agent": "Mozilla/5.0"}

# Résultats résumés par Claude : les poids lourds et les grands noms des semi-conducteurs / de l'IA
SUMMARY = earnings.MEGA | {"AMD", "MU", "ASML", "TSM", "NFLX", "PLTR"}
FED = re.compile(r"federal funds rate|fomc statement|rate decision", re.I)


# --- Outils ---------------------------------------------------------------------
def now_paris():
    if os.getenv("NOW"):
        return datetime.fromisoformat(os.environ["NOW"]).replace(tzinfo=TZ)
    return datetime.now(TZ)


def bars(sym, rng="5d", interval="5m"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={interval}&includePrePost=true"
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(d["timestamp"]):
        if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
            continue
        out.append((datetime.fromtimestamp(t, timezone.utc).astimezone(TZ),
                    q["open"][i], q["high"][i], q["low"][i], q["close"][i]))
    return out, d["meta"]


def num(x, d=0):
    s = f"{x:,.{d}f}".replace(",", " ")
    return s.replace(".", ",")


def pct(x):
    return f"{x:+.2f} %".replace(".", ",")


def post(url, text, image=None):
    if DRY_RUN or not url:
        print(f"[Discord] {text}\n[image] {image}\n")
        return
    boundary = uuid.uuid4().hex
    parts = [(f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
              f"Content-Type: application/json\r\n\r\n").encode() + json.dumps({"content": text[:1990]}).encode() + b"\r\n"]
    if image:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="{image.name}"\r\n'
                      f"Content-Type: image/png\r\n\r\n").encode() + image.read_bytes() + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "eco-calendar-bot/2.0"})
    urllib.request.urlopen(req, timeout=60).read()
    print(f"Publié sur Discord : {text.splitlines()[0]}")


def fire(text):
    if DRY_RUN or not (FIRE_URL and FIRE_TOKEN):
        print(f"[Routine] {text}\n")
        return
    req = urllib.request.Request(FIRE_URL, data=json.dumps({"text": text}).encode(), headers={
        "Authorization": f"Bearer {FIRE_TOKEN}", "anthropic-beta": "experimental-cc-routine-2026-04-01",
        "anthropic-version": "2023-06-01", "Content-Type": "application/json", "User-Agent": "eco-calendar-bot/2.0"})
    urllib.request.urlopen(req, timeout=30).read()
    print(f"Analyste Claude déclenché : {text.splitlines()[0]}")


def trading_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def close_time(d):
    return (19, 0) if d in EARLY_CLOSE else (22, 0)


# --- Agenda du jour (calculé une fois par jour) ----------------------------------
def build_agenda(day, state):
    key = f"agenda:{day}"
    if key in state:
        return state[key]
    ff = bot.fetch_forexfactory()
    inv = []
    if bot.FIRECRAWL_KEY:
        try:
            inv = bot.fetch_investing()
        except Exception as exc:
            print(f"Investing indisponible ({exc})")
    merged = [e for e in bot.merge(ff, inv) if e["dt"].date() == day and e["cur"] == "USD"]
    macro = [{"t": e["dt"].isoformat(), "title": e["title"], "fr": translate(e)[0],
              "forecast": e["forecast"], "previous": e["previous"]}
             for e in merged if e["impact"] >= 3 and not e["speech"]]
    afternoon = [f"`{e['dt']:%H:%M}` {translate(e)[0]}" for e in sorted(merged, key=lambda e: e["dt"])
                 if e["impact"] >= 2 and e["dt"].hour >= 15 and (not e["speech"] or e["impact"] >= 3)][:5]
    try:
        earn = [{"symbol": e["symbol"], "name": e["name"], "when": e["when"]}
                for e in earnings.fetch_day(day) if e["symbol"] in SUMMARY]
    except Exception as exc:
        print(f"Résultats d'entreprises indisponibles ({exc})")
        earn = []
    agenda = {"macro": macro, "afternoon": afternoon, "earnings": earn}
    # on ne garde que l'agenda du jour dans l'état
    for k in [k for k in state if k.startswith("agenda:")]:
        del state[k]
    state[key] = agenda
    print(f"Agenda du {day} : {len(macro)} chiffre(s) US majeur(s), {len(earn)} résultat(s) suivi(s).")
    return agenda


# --- Graphique (bougies 15 min + niveaux) -----------------------------------------
def chart_png(candles, levels, title, name):
    """candles : [(dt, o, h, l, c)] ; levels : [(libellé, prix, couleur)]."""
    if len(candles) < 5:
        return None
    W, H, L, R, T, B = 1600, 860, 30, 200, 70, 50
    prices = [p for c in candles for p in c[2:4]] + [lv[1] for lv in levels]
    lo, hi = min(prices), max(prices)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    y = lambda p: T + (hi - p) / (hi - lo) * (H - T - B)
    step = (W - L - R) / len(candles)
    svg = []
    for i, (dt, o, h, l, c) in enumerate(candles):
        x = L + i * step + step / 2
        col = "#22c55e" if c >= o else "#ef4444"
        svg.append(f'<line x1="{x:.1f}" y1="{y(h):.1f}" x2="{x:.1f}" y2="{y(l):.1f}" stroke="{col}" stroke-width="1.6"/>')
        top, bot_ = y(max(o, c)), y(min(o, c))
        svg.append(f'<rect x="{x - step * 0.35:.1f}" y="{top:.1f}" width="{step * 0.7:.1f}" '
                   f'height="{max(bot_ - top, 1.2):.1f}" fill="{col}"/>')
        if dt.minute == 0 and dt.hour % 3 == 0:
            svg.append(f'<text x="{x:.1f}" y="{H - 18}" fill="#7f8aa0" font-size="18" text-anchor="middle">{dt:%Hh}</text>')
    label_y = []  # étiquettes espacées d'au moins 24 px pour rester lisibles
    for label, p, col in sorted(levels, key=lambda lv: -lv[1]):
        yy = y(p)
        ty = max(yy + 6, (label_y[-1] + 24) if label_y else 0)
        label_y.append(ty)
        svg.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{W - R + 10}" y2="{yy:.1f}" stroke="{col}" stroke-width="2" stroke-dasharray="8 6"/>')
        svg.append(f'<text x="{W - R + 18}" y="{ty:.1f}" fill="{col}" font-size="19" font-weight="700">{label} {num(p)}</text>')
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;700;800&display=swap" rel="stylesheet">
<style>body{{margin:0;width:{W}px;height:{H}px;background:#070a10;font-family:Inter,"Segoe UI",sans-serif}}
text{{font-family:Inter,"Segoe UI",sans-serif}}</style></head><body>
<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg">
<text x="{L}" y="44" fill="#f3f5f9" font-size="30" font-weight="800">{title}</text>
{''.join(svg)}</svg></body></html>"""
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / name
    src = out.with_suffix(".html")
    src.write_text(page, encoding="utf-8")
    import subprocess
    chrome = bot.find_chrome()
    if not chrome:
        return None
    out.unlink(missing_ok=True)
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--virtual-time-budget=6000", f"--window-size={W},{H}",
                    f"--screenshot={out.resolve()}", src.resolve().as_uri()], capture_output=True, timeout=120)
    for _ in range(30):
        if out.exists() and out.stat().st_size > 5000:
            return out
        time.sleep(0.5)
    return None


def session_levels(nq, today):
    """Plus haut / plus bas / clôture de la séance US précédente, et plus haut / plus bas de la nuit."""
    prev_days = sorted({c[0].date() for c in nq if c[0].date() < today and trading_day(c[0].date())})
    prev = prev_days[-1] if prev_days else None
    lv = {}
    if prev:
        ch, cm = close_time(prev)
        rth = [c for c in nq if c[0].date() == prev and (c[0].hour, c[0].minute) >= (15, 30) and (c[0].hour, c[0].minute) < (ch, cm)]
        if rth:
            lv["veille_h"], lv["veille_b"], lv["veille_c"] = max(c[2] for c in rth), min(c[3] for c in rth), rth[-1][4]
    night = [c for c in nq if c[0].date() == today and c[0].hour < 15 or (c[0].date() == today and c[0].hour == 15 and c[0].minute < 30)]
    if night:
        lv["nuit_h"], lv["nuit_b"] = max(c[2] for c in night), min(c[3] for c in night)
    return lv


# --- Tâches ---------------------------------------------------------------------
def task_premarket(now, state, agenda):
    key = f"premarket:{now.date()}"
    if key in state or not trading_day(now.date()) or not (15, 0) <= (now.hour, now.minute) < (15, 30):
        return
    state[key] = now.isoformat()
    nq, meta = bars("NQ=F", "5d", "15m")
    last = nq[-1][4]
    lv = session_levels(nq, now.date())
    ctx = []
    from market_snapshot import quote
    for sym, label, fmt in [("^VIX", "VIX", lambda v: num(v, 1)), ("^TNX", "Taux 10 ans", lambda v: num(v, 2) + " %"),
                            ("CL=F", "Pétrole", lambda v: num(v, 1) + " $"), ("DX-Y.NYB", "Dollar", lambda v: num(v, 1))]:
        try:
            q = quote(sym)
            ctx.append(f"{label} {fmt(q['dernier'])} ({pct(q['var_%'])})")
        except Exception:
            pass
    ref = lv.get("veille_c")
    lines = [f"🎯 **Avant l'ouverture US** · {now:%H:%M}",
             f"Nasdaq 100 (fut.) **{num(last)}**" + (f" · {pct((last / ref - 1) * 100)} vs clôture d'hier" if ref else "")]
    if lv:
        lines.append("📏 **Niveaux** : " + " · ".join(filter(None, [
            f"veille H {num(lv['veille_h'])} / B {num(lv['veille_b'])} / C {num(lv['veille_c'])}" if "veille_h" in lv else "",
            f"nuit H {num(lv['nuit_h'])} / B {num(lv['nuit_b'])}" if "nuit_h" in lv else ""])))
    if ctx:
        lines.append("🌡️ " + " · ".join(ctx))
    recap = state.get(f"recap:{now.date()}", [])
    if recap:
        lines.append("📊 **Déjà publié** : " + " | ".join(" ; ".join(r) for r in recap).replace("• ", ""))
    if agenda["afternoon"]:
        lines.append("📅 **Cet après-midi** : " + " · ".join(agenda["afternoon"]))
    tonight = [e["name"] for e in agenda["earnings"] if e["when"] != "pre"]
    if tonight:
        lines.append("🏢 **Ce soir** : " + ", ".join(tonight))
    if now.date() in EARLY_CLOSE:
        lines.append("⏰ Fermeture anticipée à 19h00.")
    since = now - timedelta(hours=30)
    candles = [c for c in nq if c[0] >= since]
    levels = [(n, lv[k], col) for n, k, col in [("Veille H", "veille_h", "#f2b94b"), ("Veille B", "veille_b", "#f2b94b"),
                                                 ("Clôture", "veille_c", "#94a3b8"), ("Nuit H", "nuit_h", "#38bdf8"),
                                                 ("Nuit B", "nuit_b", "#38bdf8")] if k in lv]
    img = chart_png(candles, levels, f"Nasdaq 100 (contrats à terme) · bougies 15 min · {now:%d/%m %H:%M}", "avant-ouverture.png")
    post(WEBHOOK_NASDAQ, "\n".join(lines), img)
    try:
        fire("TÂCHE: plan\n" + "\n".join(lines))
    except Exception as exc:
        print(f"Plan de séance non déclenché ({exc})")


def parse_num(v):
    m = re.search(r"-?\d+(?:[.,]\d+)?", v or "")
    return float(m.group().replace(",", ".")) if m else None


NY = ZoneInfo("America/New_York")
NASDAQ_ECO = "https://api.nasdaq.com/api/calendar/economicevents?date={}"


def nasdaq_actuals(day):
    """Chiffres publiés du jour (source gratuite, interrogeable toutes les 15 s). L'API range chaque journée
    sous la date du lendemain et donne les heures de New York."""
    req = urllib.request.Request(NASDAQ_ECO.format((day + timedelta(days=1)).isoformat()), headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "application/json"})
    rows = ((json.load(urllib.request.urlopen(req, timeout=15)).get("data") or {}).get("rows")) or []
    out = []
    for r in rows:
        actual = (r.get("actual") or "").replace("&nbsp;", "").strip()
        if r.get("country") != "United States" or not actual or not re.match(r"\d{1,2}:\d{2}$", r.get("gmt") or ""):
            continue
        h, m = map(int, r["gmt"].split(":"))
        dt = datetime(day.year, day.month, day.day, h, m, tzinfo=NY).astimezone(TZ)
        out.append({"dt": dt, "title": r.get("eventName", ""), "actual": actual})
    return out


def match_actuals(evs, t_dt, found):
    """Associe chaque annonce de l'agenda à un chiffre publié à la même heure (± 5 min)."""
    actuals = {}
    same_time = [x for x in found if abs((x["dt"] - t_dt).total_seconds()) <= 300]
    for e in evs:
        best = max(same_time, key=lambda x: bot.similar({"title": e["title"]}, x), default=None)
        if best and bot.similar({"title": e["title"]}, best) >= 0.3:
            actuals[e["title"]] = best["actual"]
    return actuals


def task_macro(now, state, agenda):
    slots = {}
    for e in agenda["macro"]:
        slots.setdefault(e["t"], []).append(e)
    for t, evs in sorted(slots.items()):
        t_dt = datetime.fromisoformat(t)
        key = f"macro:{t}"
        if key in state or now < t_dt - timedelta(minutes=6) or now > t_dt + timedelta(minutes=45):
            continue
        # Veille active : on attend l'heure exacte, puis on interroge la source toutes les 15 s.
        live = not os.getenv("NOW")
        if live and datetime.now(TZ) < t_dt:
            wait = (t_dt - datetime.now(TZ)).total_seconds()
            print(f"Annonce de {t_dt:%H:%M} : veille active ({int(wait)} s d'attente).")
            time.sleep(wait)
        deadline = max(datetime.now(TZ), t_dt) + timedelta(minutes=8)
        actuals, first_seen = {}, None
        while True:
            try:
                actuals = match_actuals(evs, t_dt, nasdaq_actuals(t_dt.date()))
            except Exception as exc:
                print(f"Source Nasdaq indisponible ({exc})")
            if actuals and first_seen is None:
                first_seen = time.time()
            complete = len(actuals) == len(evs)
            # tout est là, ou une partie est là depuis 30 s : on publie sans attendre davantage
            if complete or (first_seen and time.time() - first_seen > 30) or not live or datetime.now(TZ) > deadline:
                break
            time.sleep(15)
        if not actuals and bot.FIRECRAWL_KEY:  # secours : Investing (1 crédit)
            try:
                inv = [dict(x, dt=x["dt"]) for x in bot.fetch_investing() if x["cur"] == "USD" and x.get("actual")]
                actuals = match_actuals(evs, t_dt, inv)
            except Exception as exc:
                print(f"Investing indisponible ({exc})")
        state[key] = datetime.now(TZ).isoformat()
        if not actuals:
            print(f"Annonce de {t_dt:%H:%M} : chiffres introuvables.")
            continue
        lines = [f"📊 **{t_dt:%H:%M} · Chiffres US**"]
        for e in evs:
            a = actuals.get(e["title"])
            if not a:
                continue
            fa, ff = parse_num(a), parse_num(e["forecast"])
            if fa is None or ff is None:
                tag = ""
            elif abs(fa - ff) < 1e-9:
                tag = " · = conforme"
            else:
                tag = " · ▲ au-dessus" if fa > ff else " · ▼ en dessous"
            prev = f" (prévu {bot.fr_num(e['forecast'])})" if e["forecast"] else ""
            lines.append(f"• **{e['fr']}** : **{bot.fr_num(a)}**{prev}{tag}")
        try:
            nq, _ = bars("NQ=F", "1d", "1m")
            before = [c for c in nq if c[0] <= t_dt]
            if before and nq[-1][0] > t_dt:
                p0, p1 = before[-1][4], nq[-1][4]
                lines.append(f"📈 Nasdaq 100 depuis {t_dt:%H:%M} : **{pct((p1 / p0 - 1) * 100)}** ({num(p0)} → {num(p1)})")
        except Exception:
            pass
        delay = int((datetime.now(TZ) - t_dt).total_seconds())
        print(f"Annonce de {t_dt:%H:%M} : publiée {delay} s après l'heure.")
        post(WEBHOOK_ALERTES, "\n".join(lines))
        state.setdefault(f"recap:{t_dt.date()}", []).append([l for l in lines[1:] if not l.startswith("📈")])
        if any(FED.search(e["title"]) for e in evs):
            fire(f"TÂCHE: fed\nDécision de politique monétaire de la Fed publiée à {t_dt:%H:%M} (heure de Paris) le {t_dt:%d/%m/%Y}.\n"
                 + "\n".join(lines[1:]))


def task_earnings(now, state, agenda):
    groups = {"pre": [e for e in agenda["earnings"] if e["when"] == "pre"],
              "post": [e for e in agenda["earnings"] if e["when"] != "pre"]}
    for when, (h, m) in (("pre", (14, 0)), ("post", (22, 20))):
        key = f"earn:{now.date()}:{when}"
        evs = groups[when]
        if not evs or key in state or not (h, m) <= (now.hour, now.minute) < (h + 1, m):
            continue
        state[key] = now.isoformat()
        names = ", ".join(f"{e['name']} ({e['symbol']})" for e in evs)
        moment = "avant l'ouverture" if when == "pre" else "après la clôture"
        fire(f"TÂCHE: resultats\nRésultats publiés {moment} le {now:%d/%m/%Y} : {names}.")


def task_bilan(now, state, agenda):
    key = f"bilan:{now.date()}"
    ch, cm = close_time(now.date())
    start, end = (ch, cm + 30) if cm + 30 < 60 else (ch + 1, cm - 30), (ch + 1, 30)
    if key in state or not trading_day(now.date()) or not start <= (now.hour, now.minute) < end:
        return
    state[key] = now.isoformat()
    nq, _ = bars("NQ=F", "5d", "15m")
    rth = [c for c in nq if c[0].date() == now.date() and (15, 30) <= (c[0].hour, c[0].minute) < (ch, cm)]
    if not rth:
        return
    lv = session_levels(nq, now.date())
    o, c = rth[0][1], rth[-1][4]
    hi, lo = max(x[2] for x in rth), min(x[3] for x in rth)
    hi_t = next(x[0] for x in rth if x[2] == hi)
    lo_t = next(x[0] for x in rth if x[3] == lo)
    ref = lv.get("veille_c")
    lines = [f"🌙 **Bilan de la séance** · {now:%d/%m}",
             f"Nasdaq 100 (fut.) clôture **{num(c)}**" + (f" · **{pct((c / ref - 1) * 100)}** vs veille" if ref else "")
             + f" · ouverture {num(o)}",
             f"📏 Plus haut {num(hi)} ({hi_t:%H:%M}) · plus bas {num(lo)} ({lo_t:%H:%M}) · amplitude {pct((hi / lo - 1) * 100).lstrip('+')}"]
    recap = state.get(f"recap:{now.date()}", [])
    if recap:
        lines.append("📊 **Chiffres du jour** : " + " | ".join(" ; ".join(r) for r in recap).replace("• ", ""))
    tonight = [e["name"] for e in agenda["earnings"] if e["when"] != "pre"]
    if tonight:
        lines.append("🏢 **Résultats ce soir** : " + ", ".join(tonight) + " (résumé à suivre)")
    candles = [x for x in nq if x[0].date() == now.date() and (8, 0) <= (x[0].hour, x[0].minute) < (ch, cm)]
    levels = [(n, lv[k], col) for n, k, col in [("Veille H", "veille_h", "#f2b94b"), ("Veille B", "veille_b", "#f2b94b"),
                                                 ("Clôture veille", "veille_c", "#94a3b8")] if k in lv]
    img = chart_png(candles, levels, f"Nasdaq 100 (contrats à terme) · séance du {now:%d/%m}", "bilan.png")
    post(WEBHOOK_NASDAQ, "\n".join(lines), img)


def main():
    now = now_paris()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    try:
        if now.hour >= 7 and now.weekday() < 5:
            agenda = build_agenda(now.date(), state)
            for task in (task_premarket, task_macro, task_earnings, task_bilan):
                try:
                    task(now, state, agenda)
                except Exception as exc:
                    print(f"{task.__name__} en échec : {exc}")
        else:
            print("Rien de prévu à cette heure.")
    finally:
        # ménage : 4 jours d'historique
        cutoff = (now.date() - timedelta(days=4)).isoformat()
        state = {k: v for k, v in state.items() if not re.search(r"\d{4}-\d{2}-\d{2}", k)
                 or re.search(r"\d{4}-\d{2}-\d{2}", k).group() >= cutoff}
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
