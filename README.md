# Bot calendrier économique

Chaque matin à **7h (heure de Paris)**, envoie sur Discord le calendrier économique du jour :
texte + visuel, gratuitement via GitHub Actions.

- **ForexFactory** (flux gratuit) + **Investing** (via Firecrawl, 1 crédit/jour) fusionnés :
  une annonce importante oubliée par l'un est ajoutée, on garde l'impact le plus fort.
- Annonces à impact fort et moyen, traduites en français, temps forts mis en avant.

## Configuration

**Settings → Secrets and variables → Actions**

| Secret | Valeur |
|---|---|
| `DISCORD_WEBHOOK_URL` | URL du webhook du salon Discord |
| `FIRECRAWL_API_KEY` | Clé API Firecrawl (facultatif : sans elle, ForexFactory seul) |

| Variable (facultative) | Défaut |
|---|---|
| `CURRENCIES` | `USD,EUR,GBP` |
| `SEND_AT` | `07:00` |

## Tester

**Actions → Calendrier économique → Run workflow** : envoie immédiatement.

En local : `FORCE=1 DRY_RUN=1 python bot.py` (affiche le texte, génère `out/calendrier.png`).
