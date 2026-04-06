#!/bin/bash
# ─────────────────────────────────────────────────────────────
# start.sh — Lance le bridge WhatsApp + le backend FastAPI
# ─────────────────────────────────────────────────────────────
set -e

PORT=${PORT:-10000}
DATA_DIR=${DATA_DIR:-/data}

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║      Digital Twin AI — Démarrage         ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Backend  → port ${PORT}                 "
echo "║  Bridge   → port 3001 (interne)          "
echo "║  Data dir → ${DATA_DIR}                  "
echo "╚══════════════════════════════════════════╝"
echo ""

# Créer le dossier auth pour WhatsApp
mkdir -p "${DATA_DIR}/.wa_auth"

# ── 1. Lancer le bridge WhatsApp en arrière-plan ─────────────
echo "🟡 Démarrage du bridge WhatsApp (port 3001)..."
AUTH_DIR="${DATA_DIR}/.wa_auth" \
TWIN_API_URL="http://localhost:${PORT}" \
WA_BRIDGE_PORT=3001 \
node /app/whatsapp-bridge/index.js &

BRIDGE_PID=$!
echo "✅ Bridge PID: ${BRIDGE_PID}"

# Attendre que le bridge soit prêt (max 15s)
echo "⏳ En attente du bridge..."
for i in $(seq 1 15); do
  if curl -s http://localhost:3001/health > /dev/null 2>&1; then
    echo "✅ Bridge WhatsApp prêt !"
    break
  fi
  sleep 1
done

# ── 2. Lancer le backend FastAPI (foreground) ─────────────────
echo ""
echo "🟡 Démarrage du backend FastAPI (port ${PORT})..."
cd /app/backend
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
