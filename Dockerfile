# ─────────────────────────────────────────────────────────────
# Dockerfile — Digital Twin AI (Backend Python + Bridge Node.js)
# Un seul container qui tourne les deux services
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── Installer Node.js 20 ──────────────────────────────────────
RUN apt-get update && \
    apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dépendances Python ────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Dépendances Node.js (bridge) ─────────────────────────────
COPY whatsapp-bridge/package*.json whatsapp-bridge/
RUN cd whatsapp-bridge && npm install --production

# ── Code source ───────────────────────────────────────────────
COPY backend/     backend/
COPY whatsapp-bridge/ whatsapp-bridge/

# ── Dossier data (volume Render monté ici) ────────────────────
RUN mkdir -p /data/.wa_auth

# ── Script de démarrage ───────────────────────────────────────
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
