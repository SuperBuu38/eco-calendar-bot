"""Agenda d'une séance à venir : chiffres US importants, résultats des poids lourds, dates spéciales.

Usage : python agenda.py [AAAA-MM-JJ]   (par défaut : la prochaine séance)
"""

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import bot
import earnings
from special_dates import HOLIDAYS, notes_for
from translations import translate

TZ = ZoneInfo("Europe/Paris")


def next_session(d):
    d += timedelta(days=1)
    while d.weekday() >= 5 or d in HOLIDAYS:
        d += timedelta(days=1)
    return d


if __name__ == "__main__":
    now = datetime.now(TZ)
    day = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else (
        now.date() if now.hour < 12 and now.weekday() < 5 else next_session(now.date()))
    print(f"Séance du {day:%A %d/%m/%Y}")
    try:
        evs = [e for e in bot.fetch_forexfactory() if e["dt"].date() == day and e["cur"] in ("USD", "EUR") and e["impact"] >= 2]
        if not evs and day > now.date() + timedelta(days=2):
            print("(calendrier macro pas encore publié pour ce jour : vois ff_calendar_nextweek.json)")
        for e in sorted(evs, key=lambda e: e["dt"]):
            imp = "FORT" if e["impact"] >= 3 else "moyen"
            print(f"  {e['dt']:%H:%M} {e['cur']} [{imp}] {translate(e)[0]} — prévu {e['forecast'] or '-'} · préc. {e['previous'] or '-'}")
    except Exception as exc:
        print(f"  calendrier macro indisponible ({exc})")
    try:
        for e in earnings.fetch_day(day):
            print(f"  Résultats : {e['name']} ({e['symbol']}) — {e['when_label']}{' ⭐ poids lourd' if e['mega'] else ''}")
    except Exception as exc:
        print(f"  résultats indisponibles ({exc})")
    for n in notes_for(day):
        print("  " + n.replace("**", ""))
