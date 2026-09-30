"""Bot calendrier économique -> Discord.

Chaque matin (lancé vers 6h45 par GitHub Actions) :
  1. récupère ForexFactory (flux gratuit) et Investing (via Firecrawl, 1 crédit) ;
  2. fusionne les deux calendriers (ajoute ce que l'un a oublié, garde l'impact le plus fort) ;
  3. génère le visuel (HTML -> PNG avec Chrome sans interface) ;
  4. attend 7h00 puis envoie texte + image sur Discord.

Test local : FORCE=1 DRY_RUN=1 python bot.py   (DAY=2026-10-01 pour choisir le jour)
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from translations import CURRENCY_COUNTRY, translate

ROOT = Path(__file__).parent
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
INVESTING_URL = "https://www.investing.com/economic-calendar/"
FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"

# --- Réglages -----------------------------------------------------------------
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Paris"))
CURRENCIES = [c.strip().upper() for c in os.getenv("CURRENCIES", "USD,EUR,GBP").split(",") if c.strip()]
SEND_AT = os.getenv("SEND_AT", "07:00")
FORCE = os.getenv("FORCE", "").lower() in ("1", "true", "yes")
DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
MAX_ROWS = 10
STATE_FILE = Path(os.getenv("STATE_DIR", "state")) / "state.json"

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
FIRECRAWL_KEY = os.getenv("FIRECRAWL_API_KEY", "")

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_COURT = ["JANV.", "FÉVR.", "MARS", "AVR.", "MAI", "JUIN", "JUIL.", "AOÛT", "SEPT.", "OCT.", "NOV.", "DÉC."]
FLAGS = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CHF": "🇨🇭",
         "CAD": "🇨🇦", "AUD": "🇦🇺", "NZD": "🇳🇿", "CNY": "🇨🇳"}
UA = {"User-Agent": "eco-calendar-bot/2.0"}


# --- Sources ------------------------------------------------------------------
def http_json(url, payload=None, headers=None, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    h = dict(UA, **(headers or {}))
    if data:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def fetch_forexfactory():
    events = []
    for e in http_json(FF_URL):
        impact = {"High": 3, "Medium": 2, "Low": 1}.get(e.get("impact"))
        if not impact:
            continue  # jours fériés, etc.
        events.append({
            "dt": datetime.fromisoformat(e["date"]).astimezone(TZ),
            "cur": e["country"].upper(),
            "title": e["title"],
            "impact": impact,
            "forecast": e.get("forecast", ""),
            "previous": e.get("previous", ""),
            "speech": "speaks" in e["title"].lower() or "testifies" in e["title"].lower(),
            "src": {"FF"},
        })
    return events


def fetch_investing():
    """Page Investing via Firecrawl ; les données sont dans le JSON __NEXT_DATA__."""
    res = http_json(FIRECRAWL_URL, {"url": INVESTING_URL, "formats": ["rawHtml"], "maxAge": 0},
                    headers={"Authorization": f"Bearer {FIRECRAWL_KEY}"})
    raw = (res.get("data") or {}).get("rawHtml", "")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw, re.S)
    if not m:
        raise RuntimeError("données Investing introuvables dans la page")
    found = {}

    def walk(o):
        if isinstance(o, dict):
            if "occurrenceId" in o and "importance" in o and "time" in o:
                found[o["occurrenceId"]] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    events = []
    for o in found.values():
        suffix = o.get("suffix") or ""
        events.append({
            "dt": datetime.fromisoformat(o["time"].replace("Z", "+00:00")).astimezone(TZ),
            "cur": (o.get("currency") or "").upper(),
            "title": f"{o.get('event', '')} {suffix}".strip(),
            "impact": int(o.get("importance") or 1),
            "forecast": o.get("forecast") or "",
            "previous": o.get("previous") or "",
            "speech": bool(o.get("isSpeech")),
            "src": {"INV"},
        })
    return events


# --- Fusion -------------------------------------------------------------------
_REPL = [(r"m/m", " mom "), (r"y/y", " yoy "), (r"q/q", " qoq "), (r"\bnon-farm\b", "nonfarm"),
         (r"\bnfp\b", "nonfarm payrolls")]
_DROP = {"prelim", "final", "flash", "preliminary", "revised", "the", "of", "s", "sa", "nsa"}


def tokens(title):
    t = title.lower()
    for a, b in _REPL:
        t = re.sub(a, b, t)
    t = re.sub(r"\((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|q[1-4])\)", " ", t)  # période « (Sep) »
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return {w for w in t.split() if w not in _DROP}


_PERIODS = {"mom", "yoy", "qoq"}


def similar(a, b):
    ta, tb = tokens(a["title"]), tokens(b["title"])
    if not ta or not tb:
        return 0.0
    pa, pb = ta & _PERIODS, tb & _PERIODS
    if pa and pb and pa != pb:
        return 0.0  # m/m et a/a sont deux chiffres différents
    return len(ta & tb) / len(ta | tb)


def merge(ff, inv):
    """Part de ForexFactory, complète et corrige avec Investing."""
    merged = [dict(e) for e in ff]
    used = set()
    for m in merged:
        best, score = None, 0.0
        for i, e in enumerate(inv):
            if i in used or e["cur"] != m["cur"] or e["dt"].date() != m["dt"].date():
                continue
            s = similar(m, e)
            if abs((e["dt"] - m["dt"]).total_seconds()) <= 300:
                s += 0.2  # même heure : bonus
            if s > score:
                best, score = i, s
        if best is not None and score >= 0.6:
            e = inv[best]
            used.add(best)
            m["src"] = {"FF", "INV"}
            m["impact"] = max(m["impact"], e["impact"])
            m["dt"] = e["dt"]  # Investing est plus précis sur les heures officielles
            m["forecast"] = e["forecast"] or m["forecast"]
            m["previous"] = e["previous"] or m["previous"]
    # annonces importantes qu'Investing est seul à avoir
    for i, e in enumerate(inv):
        if i not in used and e["impact"] >= 3:
            merged.append(dict(e))
    return merged


def select(events, day):
    out = [e for e in events if e["dt"].date() == day and e["cur"] in CURRENCIES and e["impact"] >= 2]
    # doublons (ex. « Core PCE m/m » et « y/y » à la même heure) : on garde tout, trié
    out.sort(key=lambda e: (e["dt"], -e["impact"]))
    if len(out) > MAX_ROWS:
        keep = sorted(out, key=lambda e: (-e["impact"], e["dt"]))[:MAX_ROWS]
        out = sorted(keep, key=lambda e: (e["dt"], -e["impact"]))
    return out


def pick_highlights(events):
    """Temps forts : les annonces à fort impact, sinon les meilleures à impact moyen."""
    def score(e):
        s = 0
        if e["cur"] == "USD":
            s += 2
        if not e["speech"]:
            s += 1
        t = e["title"].lower()
        if any(k in t for k in ("lagarde", "powell", "bailey", "cpi", "ism", "claims", "payroll", "pmi")):
            s += 2
        return s
    high = [e for e in events if e["impact"] >= 3]
    pool = high or events
    if not high and len(events) <= 3:
        return set()
    ranked = sorted(pool, key=lambda e: (-score(e), e["dt"]))
    return {id(e) for e in ranked[:3]}


# --- Rendu --------------------------------------------------------------------
def fr_num(v):
    return v.replace(".", ",") if v else ""


def fr_date(d):
    return f"{JOURS[d.weekday()]} {d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]}"


def build_text(day, events, hot):
    lines = [f"📅 **Calendrier économique — {fr_date(day)}** *(heure de Paris)*", ""]
    if not events:
        lines.append("Aucune annonce importante aujourd'hui sur " + ", ".join(CURRENCIES) + ". Journée calme 😌")
        return "\n".join(lines)
    for e in events:
        fr, _ = translate(e)
        icon = "🔴" if e["impact"] >= 3 else "🟠"
        nums = []
        if e["forecast"]:
            nums.append(f"prévu {fr_num(e['forecast'])}")
        if e["previous"]:
            nums.append(f"préc. {fr_num(e['previous'])}")
        detail = f" — {', '.join(nums)}" if nums else ""
        star = " ⭐" if id(e) in hot else ""
        lines.append(f"`{e['dt']:%H:%M}` {icon} {FLAGS.get(e['cur'], e['cur'])} **{fr}**{detail}{star}")
    if hot:
        lines += ["", "⭐ = temps fort de la journée"]
    return "\n".join(lines)


def build_html(day, events, hot):
    tpl = (ROOT / "template.html").read_text(encoding="utf-8")
    rows = []
    for e in events:
        fr, sub = translate(e)
        cls = "row cols" + (" hot" if id(e) in hot else "") + (" high" if e["impact"] >= 3 else "")
        tag = ' <span class="tag">Temps fort</span>' if id(e) in hot else ""
        if e["speech"] or not (e["forecast"] or e["previous"]):
            right = f'<div class="speech">{"Discours" if e["speech"] else "Événement"}</div>'
        else:
            right = (f'<div class="num">{html.escape(fr_num(e["forecast"])) or "–"}</div>'
                     f'<div class="num prev">{html.escape(fr_num(e["previous"])) or "–"}</div>')
        rows.append(
            f'<div class="{cls}"><div class="time">{e["dt"]:%H:%M}</div>'
            f'<div class="cur {e["cur"]}">{e["cur"]}</div>'
            f'<div class="ev"><div class="t">{html.escape(fr)}{tag}</div><div class="s">{html.escape(sub)}</div></div>'
            f'{right}</div>')
    if not rows:
        rows.append('<div class="empty">Aucune annonce importante aujourd\'hui.<br><span>Journée calme sur '
                    + ", ".join(CURRENCIES) + "</span></div>")
    n_high = sum(e["impact"] >= 3 for e in events)
    n_med = sum(e["impact"] == 2 for e in events)
    hot_times = sorted(e["dt"] for e in events if id(e) in hot)
    if hot_times:
        a, b = f"{hot_times[0]:%H:%M}", f"{hot_times[-1]:%H:%M}"
        hot_label = f"À {a}" if a == b else f"Entre {a} et {b}"
    else:
        hot_label = "Rien de majeur"
    ordinal = '<span class="ord">er</span>' if day.day == 1 else ""
    values = {
        "TITLE": f"{JOURS[day.weekday()]} {day.day}{ordinal}{'' if ordinal else ' '}{MOIS[day.month - 1]}",
        "MONTH": MOIS_COURT[day.month - 1], "DAY": f"{day.day:02d}", "YEAR": str(day.year),
        "N_HIGH": str(n_high), "N_MED": str(n_med), "N_HOT": str(len(hot)),
        "HIGH_LABEL": "Aucune annonce majeure" if n_high == 0 else "À surveiller de près",
        "MED_LABEL": "Chiffres et discours", "HOT_LABEL": hot_label,
        "ROWS": "\n".join(rows),
    }
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def find_chrome():
    for c in (os.getenv("CHROME_BIN"), "google-chrome", "chromium", "chromium-browser",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if c and (shutil.which(c) or Path(c).exists()):
            return shutil.which(c) or c
    return None


def render_png(page_html, out):
    chrome = find_chrome()
    if not chrome:
        print("Chrome introuvable : pas de visuel.")
        return None
    out.unlink(missing_ok=True)
    src = out.with_suffix(".html")
    src.write_text(page_html, encoding="utf-8")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                    "--force-device-scale-factor=2", "--virtual-time-budget=8000",
                    "--window-size=1080,1350", f"--screenshot={out.resolve()}", src.resolve().as_uri()],
                   check=False, capture_output=True, timeout=120)
    for _ in range(30):  # Edge (Windows) rend la main avant d'avoir écrit l'image
        if out.exists() and out.stat().st_size > 10000:
            break
        time.sleep(0.5)
    return out if out.exists() and out.stat().st_size > 10000 else None


# --- Envoi --------------------------------------------------------------------
def send_discord(text, image):
    boundary = uuid.uuid4().hex
    parts = [(f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"\r\n'
              f"Content-Type: application/json\r\n\r\n").encode() + json.dumps({"content": text[:1990]}).encode() + b"\r\n"]
    if image:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; filename="calendrier.png"\r\n'
                      f"Content-Type: image/png\r\n\r\n").encode() + image.read_bytes() + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(DISCORD_WEBHOOK, data=body, headers=dict(
        UA, **{"Content-Type": f"multipart/form-data; boundary={boundary}"}))
    urllib.request.urlopen(req, timeout=60).read()


# --- Principal ----------------------------------------------------------------
def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def main():
    now = datetime.now(TZ)
    day = date.fromisoformat(os.environ["DAY"]) if os.getenv("DAY") else now.date()
    h, m = map(int, SEND_AT.split(":"))
    send_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
    state = load_state()

    if not FORCE:
        if state.get("last_sent") == day.isoformat():
            print("Déjà envoyé aujourd'hui.")
            return
        # GitHub lance le job à 2 horaires UTC (heure d'été / d'hiver) : on ignore le mauvais
        if now < send_time - timedelta(minutes=45) or now > send_time + timedelta(hours=3):
            print(f"Hors créneau ({now:%H:%M}), rien à faire.")
            return

    ff = fetch_forexfactory()
    inv = []
    if FIRECRAWL_KEY:
        try:
            inv = fetch_investing()
            print(f"Investing : {len(inv)} annonces.")
        except Exception as exc:
            print(f"Investing indisponible ({exc}), ForexFactory seul.")
    events = select(merge(ff, inv), day)
    hot = pick_highlights(events)
    added = sum(1 for e in events if e["src"] == {"INV"})
    print(f"{len(events)} annonces retenues ({added} ajoutées grâce à Investing).")

    text = build_text(day, events, hot)
    out = Path(os.getenv("OUT_DIR", ROOT / "out"))
    out.mkdir(exist_ok=True)
    image = render_png(build_html(day, events, hot), out / "calendrier.png")

    if DRY_RUN or not DISCORD_WEBHOOK:
        print(text)
        print(f"Visuel : {image}")
        return
    if not FORCE and datetime.now(TZ) < send_time:
        wait = (send_time - datetime.now(TZ)).total_seconds()
        print(f"Attente jusqu'à {SEND_AT} ({int(wait)} s)…")
        time.sleep(wait)
    send_discord(text, image)
    state["last_sent"] = day.isoformat()
    save_state(state)
    print("Message envoyé sur Discord.")


if __name__ == "__main__":
    sys.exit(main())
