"""Dates spéciales du marché US : échéances d'options, jours fériés, fermetures anticipées.

Seules les dates qui changent le comportement du Nasdaq sont signalées, et seulement le jour concerné
(ou dans le récap de la semaine).
"""

from datetime import date, timedelta

# Jours fériés NYSE/Nasdaq (marché fermé)
HOLIDAYS = {
    date(2026, 1, 1): "Nouvel An", date(2026, 1, 19): "Martin Luther King Day",
    date(2026, 2, 16): "Presidents' Day", date(2026, 4, 3): "Vendredi saint",
    date(2026, 5, 25): "Memorial Day", date(2026, 6, 19): "Juneteenth",
    date(2026, 7, 3): "Fête nationale (observée)", date(2026, 9, 7): "Labor Day",
    date(2026, 11, 26): "Thanksgiving", date(2026, 12, 25): "Noël",
    date(2027, 1, 1): "Nouvel An", date(2027, 1, 18): "Martin Luther King Day",
    date(2027, 2, 15): "Presidents' Day", date(2027, 3, 26): "Vendredi saint",
    date(2027, 5, 31): "Memorial Day", date(2027, 6, 18): "Juneteenth (observé)",
    date(2027, 7, 5): "Fête nationale (observée)", date(2027, 9, 6): "Labor Day",
    date(2027, 11, 25): "Thanksgiving", date(2027, 12, 24): "Noël (observé)",
}
# Fermetures anticipées à 19h00 heure de Paris (13h00 à New York)
EARLY_CLOSE = {
    date(2026, 11, 27): "lendemain de Thanksgiving", date(2026, 12, 24): "veille de Noël",
    date(2027, 11, 26): "lendemain de Thanksgiving",
}


def third_friday(year, month):
    d = date(year, month, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def notes_for(day):
    """Messages courts pour un jour donné (liste vide la plupart du temps)."""
    out = []
    if day in HOLIDAYS:
        out.append(f"🏖️ **Marché US fermé** ({HOLIDAYS[day]}) : volumes très faibles sur les contrats à terme.")
    if day in EARLY_CLOSE:
        out.append(f"⏰ **Fermeture anticipée du marché US à 19h00** ({EARLY_CLOSE[day]}).")
    if day == third_friday(day.year, day.month):
        if day.month in (3, 6, 9, 12):
            out.append("🧙 **Quadruple sorcière** : échéance trimestrielle des options et des contrats à terme. "
                       "Volumes et volatilité élevés, surtout en fin de séance.")
        else:
            out.append("📌 **Échéance mensuelle des options (OPEX)** : mouvements parfois brusques en fin de séance.")
    return out


def week_notes(start, days=7):
    """Résumé d'une ligne par date spéciale sur la période (pour le récap du dimanche)."""
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        label = f"{jours[d.weekday()]} {d.day:02d}/{d.month:02d}"
        if d in HOLIDAYS:
            out.append(f"🏖️ Marché US fermé {label} ({HOLIDAYS[d]})")
        if d in EARLY_CLOSE:
            out.append(f"⏰ Fermeture anticipée {label} à 19h00")
        if d == third_friday(d.year, d.month):
            out.append(f"🧙 Quadruple sorcière {label}" if d.month in (3, 6, 9, 12) else f"📌 OPEX {label}")
    return out


if __name__ == "__main__":
    for d in [date(2026, 10, 16), date(2026, 12, 18), date(2026, 11, 26), date(2026, 11, 27), date(2026, 10, 2)]:
        print(d, notes_for(d))
    print(week_notes(date(2026, 10, 12)))
