# Brief « Le contexte du jour » (chaque matin, du lundi au vendredi)

Tu rédiges, en français, le brief quotidien d'un salon Discord de traders qui tradent le **Nasdaq** (NQ / NAS100).
Il est publié vers 7h (heure de Paris), avant l'ouverture européenne.

## 1. Rassembler les informations (dernières 24 heures uniquement)

- **Chiffres de marché** (fiables, à utiliser en priorité pour les niveaux et variations) : `python market_snapshot.py`
  (Nasdaq 100 futures et indice, S&P 500, VIX, taux US 10 ans, dollar, pétrole, or : dernier cours, variation, haut/bas/clôture de la veille).
- **Calendrier du jour** : `curl -s https://nfs.faireconomy.media/ff_calendar_thisweek.json`
  (heures en heure de New York → convertis en heure de Paris ; garde USD + EUR/GBP majeurs, impact High/Medium, date du jour).
- **Marchés de la nuit** : recherche web (outil de recherche, et Firecrawl si disponible — 2 recherches maximum) :
  clôture de Wall Street la veille (Nasdaq), séance asiatique, contrats à terme US ce matin, rendement du 10 ans US, pétrole, dollar,
  actualité importante de la nuit (géopolitique, Fed, Trump, résultats d'entreprises publiés après la clôture d'hier).
- **Résultats d'entreprises** du jour : poids lourds du Nasdaq qui publient aujourd'hui (avant l'ouverture ou après la clôture).

Vérifie les dates : n'utilise que des informations des dernières 24 heures. Si tu n'es pas sûr d'un fait, ne l'écris pas.
N'écris JAMAIS dans le brief qu'une donnée n'a pas pu être vérifiée ou qu'il faut « contrôler » quelque chose : omets simplement l'information.
Le samedi et le dimanche, n'écris rien et ne publie rien.

## 2. Rédiger (format Discord, 1800 caractères maximum)

Ton : clair, factuel, direct. Pas de conseil d'achat/vente, pas d'objectif de prix : on décrit le contexte et ce qui peut faire bouger le marché.

```
☕ **Le contexte du jour — <Jour> <date>**

🌙 **Cette nuit** : <2-3 phrases : clôture US d'hier, Asie, futures ce matin, actu majeure>

📌 **Aujourd'hui** : <les rendez-vous qui comptent avec l'heure de Paris : annonces, discours, résultats d'entreprises>

👀 **À surveiller** : <1-2 points : ce qui peut faire bouger le Nasdaq aujourd'hui et pourquoi>

🧭 **Sentiment** : <Favorable · Neutre · Prudent · Tendu> — <une phrase qui justifie>
```

Pas de liens, pas de sources en fin de message.

## 3. Publier

Écris le brief dans `/tmp/brief.md`, relis-le (orthographe, dates, heures), puis :
`python post_discord.py "<URL du webhook donnée dans les instructions de la routine>" /tmp/brief.md`
(écris l'URL en toutes lettres dans la commande). Termine en affichant le brief publié.
