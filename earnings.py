"""Calendrier des résultats des entreprises qui font bouger le Nasdaq.

Source : API publique du calendrier des résultats de Nasdaq.com (gratuite, sans clé).

Modes :
  python earnings.py week    visuel + texte des résultats des 2 prochaines semaines (dimanche 18h)
Utilisé aussi par bot.py (rappel des résultats du jour dans le récap de 7h).

Test local : FORCE=1 DRY_RUN=1 python earnings.py week
"""

import html
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
TZ = ZoneInfo("Europe/Paris")
API = "https://api.nasdaq.com/api/calendar/earnings?date={}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0 Safari/537.36", "Accept": "application/json"}

# Poids lourds : les « Magnificent 7 » + Broadcom, qui pèsent à eux seuls près de la moitié du Nasdaq 100
MEGA = {"NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "AVGO", "TSLA"}
# Autres valeurs capables de faire bouger le Nasdaq (grosses pondérations, semi-conducteurs, IA)
WATCH = MEGA | {
    "NFLX", "COST", "AMD", "PLTR", "ASML", "MU", "QCOM", "INTC", "ADBE", "CSCO", "AMAT", "LRCX", "KLAC",
    "TXN", "ARM", "MRVL", "PANW", "CRWD", "INTU", "ISRG", "BKNG", "TMUS", "PEP", "SNPS", "CDNS", "ABNB",
    "SHOP", "APP", "ORCL", "TSM", "CRM", "NOW", "SMCI", "DELL",
}
SHORT_NAMES = {"GOOGL": "Alphabet (Google)", "GOOG": "Alphabet (Google)", "META": "Meta", "AMZN": "Amazon",
               "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "TSLA": "Tesla", "AVGO": "Broadcom",
               "NFLX": "Netflix", "AMD": "AMD", "MU": "Micron", "ASML": "ASML", "TSM": "TSMC", "ORCL": "Oracle",
               "COST": "Costco", "PLTR": "Palantir", "INTC": "Intel", "QCOM": "Qualcomm", "ADBE": "Adobe",
               "CSCO": "Cisco", "CRM": "Salesforce", "NOW": "ServiceNow", "ARM": "Arm"}
TIMES = {"time-pre-market": ("pre", "Avant l'ouverture"), "time-after-hours": ("post", "Après la clôture")}
BADGE = {"pre": "Avant ouverture", "post": "Après clôture", "na": "À confirmer"}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def fetch_day(d):
    req = urllib.request.Request(API.format(d.isoformat()), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = ((json.load(resp).get("data") or {}).get("rows")) or []
    out, seen = [], set()
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        if sym not in WATCH:
            continue
        key = "GOOGL" if sym == "GOOG" else sym  # une seule ligne pour Alphabet
        if key in seen:
            continue
        seen.add(key)
        when, label = TIMES.get(r.get("time"), ("na", "Horaire à confirmer"))
        cap = (r.get("marketCap") or "").replace("$", "").replace(",", "")
        out.append({
            "day": d, "symbol": key, "name": SHORT_NAMES.get(key, (r.get("name") or key).replace(", Inc.", "")
                                                           .replace(" Inc.", "").replace(" Corporation", "")).strip(),
            "when": when, "when_label": label, "eps": r.get("epsForecast") or "",
            "cap": int(cap) if cap.isdigit() else 0, "mega": key in MEGA,
        })
    order = {"pre": 0, "post": 1, "na": 2}
    return sorted(out, key=lambda e: (order[e["when"]], -e["cap"]))


def fetch_range(start, days):
    events = []
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() < 5:
            try:
                events += fetch_day(d)
            except Exception as exc:
                print(f"Résultats du {d} indisponibles ({exc})")
    return events


def upcoming_mega(start, days=45, skip_until=None):
    """Prochaine publication de chaque poids lourd sur ~6 semaines (après la fenêtre détaillée)."""
    found = {}
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() >= 5 or (skip_until and d <= skip_until):
            continue
        try:
            for e in fetch_day(d):
                if e["mega"] and e["symbol"] not in found:
                    found[e["symbol"]] = e
        except Exception as exc:
            print(f"Résultats du {d} indisponibles ({exc})")
    return sorted(found.values(), key=lambda e: e["day"])


def fr_date(d, short=False):
    if short:
        return f"{JOURS[d.weekday()][:3]}. {d.day:02d}/{d.month:02d}"
    return f"{JOURS[d.weekday()]} {d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]}"


def fr_eps(v):
    neg = v.startswith("(") or v.startswith("-")
    num = v.strip("()$- ").replace(".", ",")
    return f"{'-' if neg else ''}{num} $"


def cap_label(c):
    return f"{c / 1e12:.1f} T$".replace(".", ",") if c >= 1e12 else f"{c / 1e9:.0f} Md$"


def today_lines(day):
    """Lignes pour le récap de 7h : résultats du jour (avant l'ouverture et après la clôture)."""
    try:
        evs = fetch_day(day)
    except Exception as exc:
        print(f"Résultats du jour indisponibles ({exc})")
        return []
    lines = []
    for e in evs:
        star = "⭐ " if e["mega"] else ""
        when = {"pre": "avant l'ouverture (15h30)", "post": "après la clôture (22h)"}.get(e["when"], "horaire à confirmer")
        lines.append(f"{star}**{e['name']}** ({e['symbol']}) — {when}")
    return lines


# --- Visuel de la semaine -----------------------------------------------------
CSS = """
:root{--bg:#070a10;--panel:rgba(14,19,29,.8);--line:rgba(255,255,255,.07);--line2:rgba(255,255,255,.12);
--text:#f3f5f9;--muted:#7f8aa0;--dim:#566074;--gold:#f2b94b;--pre:#38bdf8;--post:#a78bfa}
*{box-sizing:border-box;margin:0;padding:0}
body{width:1080px;height:1350px;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",sans-serif;
font-feature-settings:"tnum" 1;overflow:hidden;position:relative;padding:60px 60px 44px;display:flex;flex-direction:column}
.g1{position:absolute;width:1000px;height:1000px;right:-420px;top:-520px;border-radius:50%;
background:radial-gradient(circle,rgba(167,139,250,.16),transparent 62%)}
.g2{position:absolute;width:1100px;height:900px;left:-500px;bottom:-520px;border-radius:50%;
background:radial-gradient(circle,rgba(56,189,248,.10),transparent 62%)}
.c{position:relative;z-index:1;display:flex;flex-direction:column;flex:1;min-height:0}
.kicker{display:inline-flex;align-items:center;gap:12px;font-size:17px;font-weight:700;letter-spacing:.22em;
text-transform:uppercase;color:var(--gold)}.kicker:before{content:"";width:28px;height:2px;background:var(--gold)}
h1{margin-top:14px;font-size:58px;line-height:1.02;font-weight:800;letter-spacing:-.035em}
.sub{margin-top:14px;font-size:20px;color:var(--muted)}
.days{margin-top:24px;display:flex;flex-direction:column;gap:12px;flex:1;min-height:0;overflow:hidden}
.day{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:12px 22px 6px}
.dh{font-size:14px;font-weight:800;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.row{display:grid;grid-template-columns:150px 80px 1fr 130px;align-items:center;gap:14px;padding:7px 0;
border-top:1px solid var(--line)}.row:first-of-type{border-top:0}
.when{font-size:12px;font-weight:800;letter-spacing:.04em;padding:6px 8px;border-radius:8px;text-align:center;white-space:nowrap}
.pre{background:rgba(56,189,248,.14);color:#8fd8ff}.post{background:rgba(167,139,250,.16);color:#cbbcff}
.na{background:rgba(255,255,255,.06);color:var(--muted)}
.sym{font-size:15px;font-weight:800;letter-spacing:.06em;color:var(--muted)}
.name{font-size:22px;font-weight:700;white-space:nowrap;display:flex;align-items:center;gap:10px}
.mega .name{color:#fff}.tag{font-size:11px;font-weight:800;letter-spacing:.14em;color:#1a1204;background:var(--gold);
padding:4px 8px;border-radius:6px;text-transform:uppercase}
.eps{text-align:right;font-size:13px;color:var(--muted)}.eps b{display:block;color:var(--text);font-size:18px}
.empty{margin:auto;text-align:center;font-size:30px;font-weight:700}.empty span{display:block;margin-top:10px;font-size:18px;color:var(--muted);font-weight:500}
.later{margin-top:14px;background:var(--panel);border:1px solid rgba(242,185,75,.35);border-radius:20px;padding:16px 22px}
.chips{display:flex;flex-wrap:wrap;gap:10px}.chip{display:inline-flex;gap:8px;align-items:baseline;font-size:15px;color:var(--muted);
background:rgba(242,185,75,.08);border:1px solid rgba(242,185,75,.25);padding:7px 12px;border-radius:10px}.chip b{color:var(--text);font-size:17px}
footer{margin-top:20px;display:flex;justify-content:space-between;font-size:15px;color:var(--muted)}
.lg{display:flex;gap:22px}.lg span{display:inline-flex;align-items:center;gap:8px}.lg i{width:12px;height:12px;border-radius:3px;display:inline-block}
"""


def build_html(start, end, events, later=(), max_rows=13):
    # On remplit l'espace disponible par priorité : poids lourds, puis plus grosses capitalisations
    budget = 1010 - (125 if later else 0)
    keep = []
    for e in sorted(events, key=lambda e: (not e["mega"], -e["cap"])):
        trial = keep + [e]
        days = {x["day"] for x in trial}
        if len(days) * 52 + len(trial) * 54 > budget:
            continue
        keep = trial
    shown = [e for e in events if e in keep]
    blocks, day = [], None
    for e in shown:
        if e["day"] != day:
            if day is not None:
                blocks.append("</div>")
            day = e["day"]
            blocks.append(f'<div class="day"><div class="dh">{fr_date(day)}</div>')
        tag = '<span class="tag">Poids lourd</span>' if e["mega"] else ""
        eps = f'BPA attendu<b>{html.escape(fr_eps(e["eps"]))}</b>' if e["eps"] else ""
        blocks.append(f'<div class="row{" mega" if e["mega"] else ""}"><div class="when {e["when"]}">'
                      f'{BADGE[e["when"]]}</div><div class="sym">{e["symbol"]}</div>'
                      f'<div class="name">{html.escape(e["name"])} {tag}</div><div class="eps">{eps}</div></div>')
    if day is not None:
        blocks.append("</div>")
    if not shown:
        blocks = ['<div class="empty">Aucun résultat majeur<br><span>pour les valeurs qui pèsent sur le Nasdaq</span></div>']
    later_html = ""
    if later:
        chips = "".join(f'<span class="chip"><b>{html.escape(e["name"])}</b>{fr_date(e["day"], True)}</span>' for e in later)
        later_html = f'<div class="later"><div class="dh">Prochains poids lourds</div><div class="chips">{chips}</div></div>'
    more = len(events) - len(shown)
    note = f" · {more} autre(s) dans le message" if more > 0 else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Résultats</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="g1"></div><div class="g2"></div><div class="c">
<div class="kicker">Nasdaq · Calendrier des résultats</div>
<h1>Les résultats à venir</h1>
<div class="sub">Du {fr_date(start)} au {fr_date(end)} · {len(events)} publication(s){note}</div>
<div class="days">{''.join(blocks)}</div>
{later_html}
<footer><div class="lg"><span><i style="background:#38bdf8"></i>Avant l'ouverture (15h30)</span>
<span><i style="background:#a78bfa"></i>Après la clôture (22h)</span></div><div>Heure de Paris · Source : Nasdaq.com</div></footer>
</div></body></html>"""


def build_text(start, end, events, later=()):
    lines = [f"🏢 **Résultats d'entreprises à venir** — du {fr_date(start, True)} au {fr_date(end, True)}", ""]
    if not events:
        lines.append("Aucun résultat majeur prévu pour les valeurs qui pèsent sur le Nasdaq.")
        return "\n".join(lines)
    day = None
    for e in events:
        if e["day"] != day:
            day = e["day"]
            lines.append(f"\n__{fr_date(day)}__")
        icon = {"pre": "🌅", "post": "🌙"}.get(e["when"], "❔")
        star = "⭐ " if e["mega"] else ""
        eps = f" — BPA attendu {fr_eps(e['eps'])}" if e["eps"] else ""
        lines.append(f"{icon} {star}**{e['name']}** ({e['symbol']}) · {e['when_label'].lower()}{eps}")
    if later:
        lines += ["", "📆 **Prochains poids lourds** : " + " · ".join(f"{e['name']} {fr_date(e['day'], True)}" for e in later)]
    try:
        from special_dates import week_notes
        specials = week_notes(start, 7)
    except Exception:
        specials = []
    if specials:
        lines += ["", "🗓️ **Dates spéciales cette semaine** : " + " · ".join(specials)]
    lines +=["", "🌅 avant l'ouverture (15h30) · 🌙 après la clôture (22h) · ⭐ poids lourd du Nasdaq"]
    return "\n".join(lines)


def main():
    import bot  # réutilise le rendu PNG et l'envoi Discord du bot principal

    now = datetime.now(TZ)
    force = os.getenv("FORCE", "").lower() in ("1", "true", "yes")
    dry = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
    state = bot.load_state()
    week_key = now.strftime("%G-W%V")
    if not force:
        if now.weekday() != 6 or now.hour < 18 or state.get("last_earnings") == week_key:
            print("Pas le moment du calendrier des résultats.")
            return
    start = now.date() + timedelta(days=1 if now.weekday() >= 5 else 0)
    if now.weekday() == 5:
        start = now.date() + timedelta(days=2)
    if os.getenv("START"):
        start = date.fromisoformat(os.environ["START"])
    end = start + timedelta(days=11)
    events = fetch_range(start, 12)
    later = upcoming_mega(end + timedelta(days=1), 35)
    print(f"{len(events)} publications retenues.")
    text = bot.chunks(build_text(start, end, events, later))
    out = Path(os.getenv("OUT_DIR", ROOT / "out"))
    out.mkdir(exist_ok=True)
    image = bot.render_png(build_html(start, end, events, later), out / "resultats.png")
    if dry or not bot.DISCORD_WEBHOOK:
        print("\n\n".join(text))
        print(f"Visuel : {image}")
        return
    bot.send_discord(text[0], image)
    for part in text[1:]:
        bot.send_discord(part, None)
    if not force:  # un envoi manuel ne bloque pas celui du dimanche
        state["last_earnings"] = week_key
        bot.save_state(state)
    print("Calendrier des résultats envoyé.")


if __name__ == "__main__":
    sys.exit(main())
