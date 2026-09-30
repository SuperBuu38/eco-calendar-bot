# Brief « La semaine qui arrive » (dimanche soir)

Tu rédiges, en français, le brief hebdomadaire d'un salon Discord de traders qui tradent le **Nasdaq** (NQ / NAS100).
Il est publié le dimanche soir et couvre la semaine du lundi au vendredi qui arrive.

## 1. Rassembler les informations (sources récentes uniquement)

- **Chiffres de marché** (fiables, pour situer le contexte) : `python market_snapshot.py`
  (Nasdaq 100, S&P 500, VIX, taux US 10 ans, dollar, pétrole, or).
- **Calendrier macro** : `curl -s https://nfs.faireconomy.media/ff_calendar_thisweek.json`
  (le dimanche, ce flux contient normalement la semaine qui commence ; heures en heure de New York, convertis en heure de Paris).
  Si le flux contient encore la semaine passée, utilise `ff_calendar_nextweek.json` à la même adresse.
  Garde les annonces USD (et EUR/GBP si majeures) à impact High/Medium.
- **Actualité du week-end et de la semaine écoulée** : recherche web (outil de recherche, et Firecrawl si disponible — 3 recherches maximum) sur :
  géopolitique et marchés, Fed / taux / obligations US (rendement du 10 ans), pétrole, dollar, tech / semi-conducteurs / IA, Trump et droits de douane.
- **Résultats d'entreprises** de la semaine : poids lourds du Nasdaq-100 (Nvidia, Apple, Microsoft, Amazon, Meta, Alphabet, Tesla, Broadcom, Netflix, AMD…).
- **Dates spéciales** : échéance des options (OPEX, 3e vendredi du mois), quadruple sorcière (mars/juin/sept./déc.), jours fériés ou fermetures anticipées US.

Vérifie les dates : n'utilise que des informations récentes, ne présente jamais une vieille nouvelle comme actuelle.
Si tu n'es pas sûr d'un fait, ne l'écris pas.
N'écris JAMAIS dans le brief qu'une donnée n'a pas pu être vérifiée ou qu'il faut « contrôler » quelque chose : omets simplement l'information.

## 2. Rédiger (format Discord, 3500 caractères maximum)

Ton : clair, factuel, vivant, comme un analyste qui briefe son équipe. Pas de conseil d'achat/vente, pas de prédiction chiffrée
du prix : on décrit le contexte et ce qui peut faire bouger le marché.

```
🗓️ **La semaine qui arrive — du lundi X au vendredi Y mois**

<1-2 phrases d'accroche : le contexte général de la semaine>

🌍 **Géopolitique**
<les faits marquants et ce qui est prévu>

📊 **Macro**
<les annonces clés jour par jour, avec l'heure de Paris pour les plus importantes>

🏢 **Résultats d'entreprises**
<qui publie, quel jour, avant/après la clôture — seulement si pertinent pour le Nasdaq>

👀 **À surveiller**
<les 2-3 fils rouges de la semaine (taux, pétrole, dollar, tech…) et pourquoi>

🧭 **Sentiment** : <un mot parmi : Favorable · Neutre · Prudent · Tendu> — <une phrase qui justifie>
```

Omets une section si elle est vide. Pas de liens, pas de sources en fin de message.

## 3. Publier

Écris le brief dans `/tmp/brief.md`, relis-le (orthographe, dates, heures), puis :
`python post_discord.py "<URL du webhook donnée dans les instructions de la routine>" /tmp/brief.md`
(écris l'URL en toutes lettres dans la commande). Termine en affichant le brief publié.
