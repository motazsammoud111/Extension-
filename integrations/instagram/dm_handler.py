"""
integrations/instagram/dm_handler.py — Instagram DMs via Graph API
Reçoit et répond aux DMs Instagram.

Prérequis :
  - Page Facebook liée à un compte Instagram Business/Creator
  - INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_PAGE_ID dans .env
  - Abonnement au webhook "messages" dans Meta for Developers

Docs : https://developers.facebook.com/docs/messenger-platform/instagram/
"""

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

IG_TOKEN      = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
IG_PAGE_ID    = os.getenv("INSTAGRAM_PAGE_ID", "")
VERIFY_TOKEN  = os.getenv("IG_VERIFY_TOKEN", "digital-twin-ig")
MY_NAME       = os.getenv("MY_NAME", "Motaz")
AUTO_REPLY    = os.getenv("IG_AUTO_REPLY", "false").lower() == "true"

IG_API_BASE   = "https://graph.facebook.com/v18.0"

engine    = PersonalityEngine(profile_path=PROF_PATH)
generator = ResponseGenerator(engine=engine)
store     = MemoryStore(db_path=str(DB_PATH))

app = FastAPI(title="Instagram Digital Twin DM Handler")


# ─────────────────────────────────────────────────────────────
# Webhook
# ─────────────────────────────────────────────────────────────

@app.get("/webhook/instagram")
async def verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("✅ Webhook Instagram vérifié")
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Token invalide")


@app.post("/webhook/instagram")
async def receive_dm(request: Request):
    """Reçoit les DMs Instagram."""
    payload = await request.json()

    try:
        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id", "")
                recipient_id = messaging.get("recipient", {}).get("id", "")
                message = messaging.get("message", {})

                # Ignorer nos propres messages
                if sender_id == IG_PAGE_ID:
                    continue

                text = message.get("text", "")
                if not text:
                    continue

                print(f"📩 Instagram DM de {sender_id}: {text[:60]}")

                # Stocker
                store.save_messages([{
                    "source": "instagram",
                    "sender": sender_id,
                    "text": text,
                    "timestamp": "",
                }], my_name=MY_NAME)

                if AUTO_REPLY:
                    result = generator.suggest(text, person_type="unknown")
                    if result.get("response"):
                        await _send_dm(sender_id, result["response"])
                        store.save_response(
                            incoming=text,
                            response=result["response"],
                            alternatives=result.get("alternatives", []),
                            person_type="unknown",
                            confidence=result.get("confidence", 0.0),
                            model=result.get("model", ""),
                        )

    except Exception as e:
        print(f"❌ Erreur Instagram webhook: {e}")

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────
# Envoi de DM
# ─────────────────────────────────────────────────────────────

async def _send_dm(recipient_id: str, text: str):
    """Envoie un DM Instagram via Messenger API."""
    url = f"{IG_API_BASE}/{IG_PAGE_ID}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    params = {"access_token": IG_TOKEN}

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, params=params)
        if resp.status_code == 200:
            print(f"✅ DM envoyé à {recipient_id}")
        else:
            print(f"❌ Erreur envoi DM: {resp.text}")


# ─────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"📸 Instagram DM Handler — Twin de {MY_NAME}")
    print(f"🔄 Auto-reply : {'ON' if AUTO_REPLY else 'OFF'}")
    uvicorn.run("dm_handler:app", host="0.0.0.0", port=8002, reload=True)
