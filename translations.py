"""Traduction des annonces en français : (titre, sous-titre)."""

import re

CURRENCY_COUNTRY = {"USD": "États-Unis", "EUR": "Zone euro", "GBP": "Royaume-Uni", "JPY": "Japon",
                    "CHF": "Suisse", "CAD": "Canada", "AUD": "Australie", "NZD": "Nouvelle-Zélande",
                    "CNY": "Chine"}

# Orateurs : nom -> (nom complet, fonction)
SPEAKERS = {
    "powell": ("Jerome Powell", "Président · Fed"),
    "lagarde": ("Christine Lagarde", "Présidente · BCE"),
    "bailey": ("Andrew Bailey", "Gouverneur · Banque d'Angleterre"),
    "schlegel": ("Martin Schlegel", "Président · BNS"),
    "ueda": ("Kazuo Ueda", "Gouverneur · Banque du Japon"),
    "waller": ("Christopher Waller", "Membre du FOMC · Fed"),
    "kashkari": ("Neel Kashkari", "Membre du FOMC · Fed"),
    "williams": ("John Williams", "Membre du FOMC · Fed"),
    "jefferson": ("Philip Jefferson", "Vice-président · Fed"),
    "bowman": ("Michelle Bowman", "Vice-présidente · Fed"),
    "goolsbee": ("Austan Goolsbee", "Membre du FOMC · Fed"),
    "schnabel": ("Isabel Schnabel", "Membre du directoire · BCE"),
    "lane": ("Philip Lane", "Chef économiste · BCE"),
    "elderson": ("Frank Elderson", "Membre du directoire · BCE"),
    "trump": ("Donald Trump", "Président des États-Unis"),
}

# (motif regex sur le titre anglais, titre FR, sous-titre FR) — le premier qui correspond gagne
RULES = [
    (r"core pce", "Inflation PCE de base", "Indicateur d'inflation préféré de la Fed"),
    (r"\bpce\b", "Inflation PCE", "Prix des dépenses de consommation"),
    (r"core cpi", "Inflation de base", "CPI hors énergie et alimentation"),
    (r"\bcpi\b|consumer price", "Inflation", "Prix à la consommation (CPI)"),
    (r"\bhicp\b", "Inflation harmonisée (IPCH)", "Prix à la consommation"),
    (r"\bppi\b|producer price", "Prix à la production (PPI)", "Inflation côté entreprises"),
    (r"adp", "Emploi privé ADP", "Créations d'emplois dans le privé"),
    (r"non-?farm (employment|payrolls)|\bnfp\b", "Emplois non agricoles (NFP)", "Créations d'emplois"),
    (r"unemployment claims|jobless claims", "Inscriptions au chômage", "Demandes hebdomadaires"),
    (r"unemployment rate", "Taux de chômage", "Marché du travail"),
    (r"unemployment change|claimant count", "Variation du chômage", "Marché du travail"),
    (r"average hourly earnings", "Salaire horaire moyen", "Pression salariale"),
    (r"jolts|job openings", "Offres d'emploi JOLTS", "Marché du travail"),
    (r"gdp price index", "Déflateur du PIB", "Inflation dans le PIB"),
    (r"\bgdp\b", "PIB", "Croissance économique"),
    (r"ism manufacturing", "ISM manufacturier", "Activité industrielle"),
    (r"ism services|ism non-manufacturing", "ISM des services", "Activité des services"),
    (r"chicago pmi", "PMI de Chicago", "Activité industrielle régionale"),
    (r"manufacturing pmi", "PMI manufacturier", "Activité industrielle"),
    (r"services pmi", "PMI des services", "Activité des services"),
    (r"composite pmi", "PMI composite", "Activité globale"),
    (r"retail sales", "Ventes au détail", "Consommation des ménages"),
    (r"personal spending", "Dépenses des ménages", "Consommation"),
    (r"personal income", "Revenus des ménages", "Consommation"),
    (r"consumer confidence|consumer sentiment", "Confiance des consommateurs", "Moral des ménages"),
    (r"durable goods", "Commandes de biens durables", "Investissement des entreprises"),
    (r"crude oil inventories", "Stocks de pétrole brut", "Rapport hebdomadaire EIA"),
    (r"trade balance", "Balance commerciale", "Exportations moins importations"),
    (r"current account", "Balance courante", "Échanges avec l'étranger"),
    (r"building permits", "Permis de construire", "Immobilier"),
    (r"housing starts", "Mises en chantier", "Immobilier"),
    (r"(new|existing|pending) home sales", "Ventes de logements", "Immobilier"),
    (r"industrial production", "Production industrielle", "Activité industrielle"),
    (r"ifo", "Climat des affaires Ifo", "Moral des entreprises allemandes"),
    (r"zew", "Sentiment économique ZEW", "Moral des investisseurs"),
    (r"fomc (statement|meeting)|federal funds rate|interest rate decision|rate decision|official bank rate|main refinancing",
     "Décision de taux", "Politique monétaire"),
    (r"fomc minutes|meeting minutes|monetary policy (meeting )?minutes", "Compte rendu de politique monétaire", "Politique monétaire"),
    (r"press conference", "Conférence de presse", "Politique monétaire"),
    (r"bond auction|bund auction|note auction", "Adjudication d'obligations", "Marché obligataire"),
]

PREFIX = {"german": "allemand", "french": "français", "italian": "italien", "spanish": "espagnol"}
PREFIX_F = {"german": "allemande", "french": "française", "italian": "italienne", "spanish": "espagnole"}
FEMININE = ("Inflation", "Balance", "Confiance", "Décision", "Adjudication", "Variation", "Production")


def _period(title):
    t = title.lower()
    if re.search(r"m/m|\(mom\)", t):
        return " (m/m)"
    if re.search(r"y/y|\(yoy\)", t):
        return " (a/a)"
    if re.search(r"q/q|\(qoq\)", t):
        return " (t/t)"
    return ""


def translate(e):
    title = e["title"]
    t = title.lower()
    country = CURRENCY_COUNTRY.get(e["cur"], e["cur"])

    if e.get("speech") or "speaks" in t or "testifies" in t:
        for key, (name, role) in SPEAKERS.items():
            if key in t:
                return f"Discours de {name}", role
        who = re.sub(r"\b(speaks|testifies)\b", "", title, flags=re.I).strip()
        return f"Discours · {who}", country

    for pattern, fr, sub in RULES:
        if re.search(pattern, t):
            for en, adj in PREFIX.items():
                if t.startswith(en):
                    fr = f"{fr} {PREFIX_F[en] if fr.startswith(FEMININE) else adj}"
                    country = {"german": "Allemagne", "french": "France",
                               "italian": "Italie", "spanish": "Espagne"}[en]
                    break
            if "prelim" in t or "flash" in t:
                fr += " (prélim.)"
            return fr + _period(title), f"{sub} · {country}"

    return title, country
