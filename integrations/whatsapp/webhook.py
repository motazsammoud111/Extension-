"""
integrations/whatsapp/webhook.py — Webhook WhatsApp Business API
Reçoit les messages WhatsApp et génère des réponses via le twin.

Prérequis :
  - Compte Meta for Developers avec WhatsApp Business API
  - WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID dans .env
  - Un tunnel HTTPS (ngrok ou Cloudflare Tunnel) pour recevoir le webhook

Docs : https://developers.facebook.com/docs/whatsapp/cloud-api/
"""

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from personality_engine import PersonalityEngine
from response_generator import ResponseGenerator
from memory_store import MemoryStore


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent.parent.parent
PROF_PATH = BASE_DIR / "data" / "personality_profile" / "profile.json"
DB_PATH   = BASE_DIR / "data" / "memory.db"

WA_TOKEN      = os.getenv("WHATSAPP_TOKEN", "")
WA_PHONE_ID   = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
VERIFY_TOKEN  = os.getenv("WHATSAPP_VERIFY_TOKEN", "digital-twin-verify")
APP_SECRET    = os.getenv("WHATSAPP_APP_SECRET", "")
MY_NAME       = os.getenv("MY_NAME", "Motaz")
AUTO_REPLY    = os.getenv("WA_AUTO_REPLY", "false").lower() == "true"

WA_API_URL    = f"https://graph.facebook.com/v18.0/{WA_PHONE_ID}/messages"

engine    = PersonalityEngine(profile_path=PROF_PATH)
generator = ResponseGenerator(engine=engine)
store     = MemoryStore(db_path=str(DB_PATH))

app = FastAPI(title="WhatsApp Digital Twin Webhook")


# ─────────────────────────────────────────────────────────────
# Vérification du webhook (Meta)
# ─────────────────────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Meta vérifie le webhook lors de la configuration."""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print(f"✅ Webhook WhatsApp vérifié")
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Token de vérification invalide")


# ─────────────────────────────────────────────────────────────
# Réception des messages
# ─────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_message(request: Request):
    """Reçoit les messages entrants WhatsApp."""
    body = await request.body()

    # Vérifier la signature Meta (sécurité)
    if APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(body, signature):
            raise HTTPException(status_code=403, detail="Signature invalide")

    payload = json.loads(body)

    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        contacts = value.get("contacts", [])

        for message in messages:
            msg_type = message.get("type", "")
            if msg_type != "text":
                continue   # Ignorer les médias pour l'instant

            from_number = message.get("from", "")
            text = message.get("text", {}).get("body", "")
            msg_id = message.get("id", "")

            # Marquer comme lu
            await _mark_read(msg_id)

            sender_name = _get_contact_name(contacts, from_number)
            print(f"📨 Message de {sender_name} ({from_number}): {text[:60]}")

            # Stocker le message
            store.save_messages([{
                "source": "whatsapp",
                "sender": sender_name or from_number,
                "text": text,
                "timestamp": "",
            }], my_name=MY_NAME)

            if AUTO_REPLY:
                # Générer et envoyer la réponse
                result = generator.suggest(text, person_type="close_friend")
                if result.get("response"):
                    await _send_message(from_number, result["response"])
                    store.save_response(
                        incoming=text,
                        response=result["response"],
                        alternatives=result.get("alternatives", []),
                        person_type="close_friend",
                        confidence=result.get("confidence", 0.0),
                        model=result.get("model", ""),
                    )

    except Exception as e:
        print(f"❌ Erreur traitement webhook: {e}")

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
# Fonctions utilitaires WhatsApp
# ─────────────────────────────────────────────────────────────

async def _send_message(to: str, text: str):
    """Envoie un message WhatsApp."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WA_API_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            print(f"❌ Erreur envoi WhatsApp: {resp.text}")
        else:
            print(f"✅ Message envoyé à {to}")


async def _mark_read(message_id: str):
    """Marque un message comme lu."""
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        await client.post(WA_API_URL, json=payload, headers=headers)


def _verify_signature(body: bytes, signature: str) -> bool:
    """Vérifie la signature HMAC-SHA256 de Meta."""
    expected = "sha256=" + hmac.new(
        APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _get_contact_name(contacts: list, phone: str) -> str:
    for c in contacts:
        if c.get("wa_id") == phone:
            return c.get("profile", {}).get("name", phone)
    return phone


# ─────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"🟢 WhatsApp Webhook — Twin de {MY_NAME}")
    print(f"📱 Auto-reply : {'ON' if AUTO_REPLY else 'OFF (mode suggestion)'}")
    print(f"🔗 Configure l'URL webhook dans Meta : https://ton-domaine.com/webhook")
    uvicorn.run("webhook:app", host="0.0.0.0", port=8001, reload=True)
