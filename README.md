# Bot calendrier économique

Envoie sur Discord et/ou Telegram, gratuitement via GitHub Actions :

- 📅 **le récap du jour** chaque matin (7h, heure de Paris) ;
- ⚠️ **une alerte ~15-30 min avant** chaque annonce importante ;
- 🗓️ **le programme de la semaine** le dimanche soir (18h).

Source : flux gratuit ForexFactory. Le bot tourne toutes les 15 min.

## Configuration

**Settings → Secrets and variables → Actions**

Secrets (au moins une destination) :

| Secret | Valeur |
|---|---|
| `DISCORD_WEBHOOK_URL` | URL du webhook du salon Discord |
| `TELEGRAM_BOT_TOKEN` | Token donné par @BotFather |
| `TELEGRAM_CHAT_ID` | ID de ta conversation Telegram |

Variables (facultatives) :

| Variable | Défaut | Exemple |
|---|---|---|
| `CURRENCIES` | `USD,EUR,GBP` | `USD,EUR,GBP,JPY,CAD` |
| `IMPACTS` | `High` | `High,Medium` |
| `RECAP_HOUR` | `7` | `8` |
| `WEEK_HOUR` | `18` | `20` |
| `ALERT_MINUTES` | `30` | `45` |

## Tester

Onglet **Actions → Calendrier économique → Run workflow**, choisir `recap`, `week` ou `alerts`.

En local : `FORCE=1 python bot.py recap` (affiche le message si aucune destination n'est configurée).
