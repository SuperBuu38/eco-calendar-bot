"""Bot calendrier économique -> Discord / Telegram.

Lancé toutes les 15 min par GitHub Actions (python bot.py), il fait en un seul passage :
  - le récap du jour, une fois par jour à partir de RECAP_HOUR
  - le programme de la semaine, le dimanche à partir de WEEK_HOUR
  - une alerte avant chaque annonce importante (fenêtre ALERT_MINUTES)

Tests manuels : python bot.py recap | week | alerts  (FORCE=1 ignore l'heure)

Source : flux gratuit ForexFactory (heure, devise, impact, prévision, précédent).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# --- Réglages (modifiables via variables d'environnement) -------------------
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Paris"))
CURRENCIES = {c.strip().upper() for c in os.getenv("CURRENCIES", "USD,EUR,GBP").split(",") if c.strip()}
IMPACTS = {i.strip().capitalize() for i in os.getenv("IMPACTS", "High").split(",") if i.strip()}
RECAP_HOUR = int(os.getenv("RECAP_HOUR", "7"))
WEEK_HOUR = int(os.getenv("WEEK_HOUR", "18"))
ALERT_MINUTES = int(os.getenv("ALERT_MINUTES", "30"))  # fenêtre d'alerte avant l'annonce
FORCE = os.getenv("FORCE", "").lower() in ("1", "true", "yes")
STATE_DIR = Path(os.getenv("STATE_DIR", "state"))
STATE_FILE = STATE_DIR / "state.json"
FEED_CACHE = STATE_DIR / "feed.json"
FEED_MAX_AGE = timedelta(hours=1)  # ForexFactory limite fortement les requêtes

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FLAGS = {"USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵", "CHF": "🇨🇭",
         "CAD": "🇨🇦", "AUD": "🇦🇺", "NZD": "🇳🇿", "CNY": "🇨🇳", "ALL": "🌍"}
IMPACT_ICON = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "Holiday": "🏖️"}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


# --- Données ----------------------------------------------------------------
def load_feed():
    """Télécharge le flux au plus une fois par heure, sinon réutilise la copie locale."""
    fresh = FEED_CACHE.exists() and (
        datetime.now().timestamp() - FEED_CACHE.stat().st_mtime < FEED_MAX_AGE.total_seconds())
    if not fresh:
        try:
            req = urllib.request.Request(FEED_URL, headers={"User-Agent": "eco-calendar-bot/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            json.loads(raw)
            FEED_CACHE.parent.mkdir(parents=True, exist_ok=True)
            FEED_CACHE.write_bytes(raw)
        except Exception as exc:  # 429, réseau… on retombe sur la copie locale
            if not FEED_CACHE.exists():
                raise
            print(f"Flux indisponible ({exc}), utilisation de la copie locale.")
    return json.loads(FEED_CACHE.read_text(encoding="utf-8"))


_events = None


def fetch_events():
    global _events
    if _events is not None:
        return _events
    raw = load_feed()
    events = []
    for e in raw:
        if e.get("country", "").upper() not in CURRENCIES:
            continue
        if e.get("impact") not in IMPACTS:
            continue
        e["dt"] = datetime.fromisoformat(e["date"]).astimezone(TZ)
        events.append(e)
    _events = sorted(events, key=lambda e: e["dt"])
    return _events


def fmt_date(d):
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"


def fmt_event(e, with_time=True):
    flag = FLAGS.get(e["country"], e["country"])
    icon = IMPACT_ICON.get(e["impact"], "")
    parts = []
    if e.get("forecast"):
        parts.append(f"prévu {e['forecast']}")
    if e.get("previous"):
        parts.append(f"préc. {e['previous']}")
    details = f" — {', '.join(parts)}" if parts else ""
    when = f"`{e['dt']:%H:%M}` " if with_time else ""
    return f"{when}{icon} {flag} **{e['title']}**{details}"


# --- Envoi ------------------------------------------------------------------
def _post_json(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "User-Agent": "eco-calendar-bot/1.0"})
    urllib.request.urlopen(req, timeout=30).read()


def _chunks(text, size):
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def send(text):
    if not DISCORD_WEBHOOK and not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        print("Aucune destination configurée, message affiché seulement :\n")
        print(text)
        return
    if DISCORD_WEBHOOK:
        for part in _chunks(text, 1900):
            _post_json(DISCORD_WEBHOOK, {"content": part})
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        # Telegram : le gras Markdown est *texte*, pas **texte**
        tg = text.replace("**", "*")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        for part in _chunks(tg, 3900):
            _post_json(url, {"chat_id": TELEGRAM_CHAT_ID, "text": part,
                             "parse_mode": "Markdown", "disable_web_page_preview": True})
    print("Message envoyé.")


# --- Modes ------------------------------------------------------------------
def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def recap(now, state):
    today_key = now.date().isoformat()
    if not FORCE and (now.hour < RECAP_HOUR or state.get("last_recap") == today_key):
        return
    state["last_recap"] = today_key
    today = [e for e in fetch_events() if e["dt"].date() == now.date()]
    header = f"📅 **Calendrier économique — {fmt_date(now)}**"
    if not today:
        body = "Aucune annonce importante aujourd'hui sur " + ", ".join(sorted(CURRENCIES)) + ". Journée calme 😌"
    else:
        body = "\n".join(fmt_event(e) for e in today)
    send(f"{header}\n{body}")


def week(now, state):
    today_key = now.date().isoformat()
    if not FORCE and not (now.weekday() == 6 and now.hour >= WEEK_HOUR
                          and state.get("last_week") != today_key):
        return
    events = [e for e in fetch_events() if e["dt"] > now]
    if not events:
        # Le dimanche, le flux peut encore être celui de la semaine passée : on réessaiera
        print("Calendrier de la semaine pas encore disponible.")
        return
    state["last_week"] = today_key
    lines = ["🗓️ **Programme de la semaine**"]
    day = None
    for e in events:
        if e["dt"].date() != day:
            day = e["dt"].date()
            lines.append(f"\n__{fmt_date(e['dt'])}__")
        lines.append(fmt_event(e))
    send("\n".join(lines))


def alerts(now, state):
    alerted = state.setdefault("alerted", {})
    limit = now + timedelta(minutes=ALERT_MINUTES)
    upcoming = [e for e in fetch_events()
                if now < e["dt"] <= limit and e["impact"] != "Holiday"]
    new = []
    for e in upcoming:
        key = f"{e['date']}|{e['country']}|{e['title']}"
        if key not in alerted:
            new.append(e)
            alerted[key] = now.isoformat()
    if new:
        lines = []
        for e in new:
            mins = int((e["dt"] - now).total_seconds() // 60)
            lines.append(f"⚠️ **Dans {mins} min** — {fmt_event(e)}")
        send("\n".join(lines))
    # on ne garde que les 7 derniers jours
    cutoff = (now - timedelta(days=7)).isoformat()
    state["alerted"] = {k: v for k, v in alerted.items() if v >= cutoff}


if __name__ == "__main__":
    modes = {"recap": recap, "week": week, "alerts": alerts}
    selected = [sys.argv[1]] if len(sys.argv) > 1 else list(modes)
    now = datetime.now(TZ)
    state = load_state()
    try:
        for name in selected:
            modes[name](now, state)
    finally:
        save_state(state)
    print(f"OK ({now:%Y-%m-%d %H:%M} {TZ.key})")
