#!/usr/bin/env bash
# Réveil lancé par une routine Claude (plus ponctuelle que le planificateur de GitHub).
# Usage : bash wake.sh calendar   (6h50 : calendrier de 7h + vérifie que le détecteur tourne)
#         bash wake.sh earnings   (dimanche 18h : calendrier des résultats)
set -u
REPO="SuperBuu38/eco-calendar-bot"
API="repos/$REPO/actions/workflows"
HOUR=$(TZ=Europe/Paris date +%H)
DOW=$(TZ=Europe/Paris date +%u)   # 1 = lundi … 7 = dimanche

dispatch() {  # $1 = fichier du workflow, puis paires clé=valeur pour les entrées
  local wf=$1; shift
  local args=(-X POST "$API/$wf/dispatches" -f ref=main)
  for kv in "$@"; do args+=(-f "inputs[${kv%%=*}]=${kv#*=}"); done
  if gh api "${args[@]}"; then echo "✅ $wf lancé"; else echo "❌ $wf : échec du lancement"; fi
}

case "${1:-}" in
  calendar)
    if [ "$HOUR" != "06" ]; then echo "Il est ${HOUR}h à Paris : mauvais créneau (heure d'été/hiver), rien à faire."; exit 0; fi
    if [ "$DOW" -le 5 ]; then dispatch bot.yml force=false; else echo "Week-end : pas de calendrier."; fi
    running=$(gh api "$API/movers.yml/runs?status=in_progress" --jq .total_count)
    queued=$(gh api "$API/movers.yml/runs?status=queued" --jq .total_count)
    if [ "$running" = "0" ] && [ "$queued" = "0" ]; then dispatch movers.yml; else echo "✅ Détecteur de mouvement déjà actif"; fi
    ;;
  earnings)
    if [ "$HOUR" != "18" ]; then echo "Il est ${HOUR}h à Paris : mauvais créneau, rien à faire."; exit 0; fi
    dispatch earnings.yml force=true
    ;;
  *) echo "Usage : bash wake.sh calendar|earnings"; exit 1 ;;
esac
