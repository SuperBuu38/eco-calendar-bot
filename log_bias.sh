#!/usr/bin/env bash
# Enregistre un biais dans data/bias.json (via le workflow « Journal des biais »), pour le tableau de bord.
# Usage : bash log_bias.sh <AAAA-MM-JJ séance visée> <haussier|baissier|neutre> <faible|moyenne|haute> <niveau ▲> <niveau ▼>
set -eu
gh api -X POST repos/SuperBuu38/eco-calendar-bot/actions/workflows/bias-log.yml/dispatches -f ref=main \
  -f "inputs[date]=$1" -f "inputs[bias]=$2" -f "inputs[confiance]=$3" -f "inputs[haut]=$4" -f "inputs[bas]=$5" \
  && echo "✅ Biais enregistré ($1 : $2, confiance $3, ▲ $4 / ▼ $5)"
