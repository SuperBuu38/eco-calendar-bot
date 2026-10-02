# Mise à jour du biais à 8h (avant l'ouverture européenne)

Le biais de la séance du jour a été publié hier soir. Vérifie s'il tient toujours après la nuit.

1. Lis le biais enregistré : `python -c "import json;print([b for b in json.load(open('data/bias.json'))][-1])"`
2. `python levels.py` et `python intraday.py 10` : où est le prix par rapport aux niveaux ▲ / ▼ du biais ? Qu'a fait la nuit (Asie, taux, pétrole) ?
3. 1 recherche Firecrawl `firecrawl_search` (`sources: ["news"]`, `tbs: "qdr:h"`) : une nouvelle importante cette nuit ?
4. Rédige **3 lignes maximum** (français, format Discord) :

```
☀️ **Biais du jour : <confirmé / affaibli / invalidé>** · <haussier / baissier / neutre>
<ce qui s'est passé cette nuit, avec un chiffre>
<le niveau clé à surveiller ce matin>
```

Si rien n'a changé, dis-le en une ligne. Pas de liens, pas de « achète / vends ».
Publie : écris dans `/tmp/maj.md` puis `python post_discord.py "<URL du webhook BIAIS>" /tmp/maj.md`
