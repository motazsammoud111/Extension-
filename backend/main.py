"""
main.py — API FastAPI du Digital Twin AI
Endpoints : /import, /personality, /suggest, /train, /stats
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
import httpx

# Ajouter le dossier backend au path
sys.path.insert(0, str(Path(__file__).parent))

from personality_engine import PersonalityEngine
from conversation_analyzer import ConversationAnalyzer, WhatsAppParser, TelegramParser, InstagramParser
from response_generator import ResponseGenerator
from memory_store import MemoryStore


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

MY_NAME      = os.getenv("MY_NAME", "Motaz")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")          # Groq gratuit pour les tests

# Origins autorisés pour CORS (Vercel + local dev)
_EXTRA_ORIGINS = os.getenv("ALLOWED_ORIGINS", "")     # ex: https://my-twin.vercel.app
ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite dev
    "http://localhost:3000",   # CRA dev
    "http://localhost:3001",   # WhatsApp bridge
    "http://127.0.0.1:5173",
]
if _EXTRA_ORIGINS:
    ALLOWED_ORIGINS += [o.strip() for o in _EXTRA_ORIGINS.split(",") if o.strip()]

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR  = DATA_DIR / "raw_conversations"
PROC_DIR = DATA_DIR / "processed"
PROF_DIR = DATA_DIR / "personality_profile"
PROF_PATH = PROF_DIR / "profile.json"
DB_PATH  = DATA_DIR / "memory.db"

for d in [RAW_DIR, PROC_DIR, PROF_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# Services (singletons)
# ─────────────────────────────────────────────────────────────

engine   = PersonalityEngine(profile_path=PROF_PATH)
analyzer = ConversationAnalyzer(my_name=MY_NAME, engine=engine)
generator = ResponseGenerator(engine=engine, api_key=GROQ_API_KEY)
store    = MemoryStore(db_path=str(DB_PATH))


# ─────────────────────────────────────────────────────────────
# App FastAPI
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Digital Twin AI",
    description=f"Agent IA qui imite le style de communication de {MY_NAME}",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# Schemas Pydantic
# ─────────────────────────────────────────────────────────────

class SuggestRequest(BaseModel):
    message: str = Field(..., description="Le message reçu auquel répondre")
    person_type: str = Field(
        "close_friend",
        description="Type d'interlocuteur : close_friend | family | colleague | client | unknown",
    )
    context_note: str = Field("", description="Note contextuelle optionnelle")
    history: Optional[List[dict]] = Field(
        None,
        description='Historique : [{"role":"user","content":"..."}, ...]',
    )

class SuggestResponse(BaseModel):
    response: str
    alternatives: List[str]
    confidence: float
    person_type: str
    model: str
    response_id: Optional[int] = None

class FeedbackRequest(BaseModel):
    response_id: int
    rating: int = Field(..., ge=-1, le=1, description="-1=mauvaise, 0=neutre, 1=bonne")
    used: bool = Field(False, description="True si la réponse a été envoyée")

class ContactRequest(BaseModel):
    name: str
    person_type: str = "unknown"
    platform: str = ""
    notes: str = ""

class TrainResponse(BaseModel):
    status: str
    messages_before: int
    messages_after: int
    profile_version: int

class ImportResponse(BaseModel):
    status: str
    file: str
    source: str
    my_messages: int
    total_messages: int
    participation_rate: float


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {
        "twin": MY_NAME,
        "status": "online",
        "messages_analyzed": engine.get_profile().total_messages_analyzed,
        "profile_version": engine.get_profile().version,
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# ── /import ───────────────────────────────────────────────────

@app.post("/import", response_model=ImportResponse, tags=["training"])
async def import_conversation(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Importe un fichier de conversation exporté.
    Formats supportés : .txt (WhatsApp), .json (Telegram/Instagram)
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in (".txt", ".json"):
        raise HTTPException(
            status_code=400,
            detail="Format non supporté. Utilise .txt (WhatsApp) ou .json (Telegram/Instagram).",
        )

    # Sauvegarder le fichier uploadé
    dest = RAW_DIR / file.filename
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    # Analyser
    try:
        report = analyzer.analyze_file(dest)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'analyse : {e}")

    if "error" in report:
        raise HTTPException(status_code=422, detail=report["error"])

    # Logger l'événement
    store.log_event("import", {
        "file": file.filename,
        "source": report.get("source"),
        "my_messages": report.get("my_messages"),
    })

    return ImportResponse(
        status="success",
        file=file.filename,
        source=report.get("source", ""),
        my_messages=report.get("my_messages", 0),
        total_messages=report.get("total_messages", 0),
        participation_rate=report.get("participation_rate", 0.0),
    )


# ── /personality ──────────────────────────────────────────────

@app.get("/personality", tags=["profile"])
def get_personality():
    """Retourne le profil de personnalité complet."""
    profile = engine.get_profile()
    return profile.to_dict()


@app.get("/personality/summary", tags=["profile"])
def get_personality_summary():
    """Retourne un résumé lisible du profil."""
    return {"summary": engine.get_profile().summary()}


@app.get("/personality/prompt-preview", tags=["profile"])
def get_prompt_preview(person_type: str = "close_friend"):
    """Retourne le system prompt qui sera envoyé à Claude (pour debug)."""
    return {"system_prompt": generator.build_system_prompt_preview(person_type)}


# ── /suggest ──────────────────────────────────────────────────

@app.post("/suggest", response_model=SuggestResponse, tags=["twin"])
def suggest_response(req: SuggestRequest):
    """
    Donne un message reçu → retourne la réponse dans ton style.
    C'est l'endpoint principal du Digital Twin.
    """
    profile = engine.get_profile()
    if profile.total_messages_analyzed == 0:
        raise HTTPException(
            status_code=428,
            detail="Aucun profil chargé. Importe d'abord des conversations via POST /import.",
        )

    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY non configurée. Vérifie ton fichier .env.",
        )

    result = generator.suggest(
        incoming_message=req.message,
        conversation_history=req.history,
        person_type=req.person_type,
        context_note=req.context_note,
    )

    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])

    # Sauvegarder en DB
    response_id = store.save_response(
        incoming=req.message,
        response=result["response"],
        alternatives=result.get("alternatives", []),
        person_type=req.person_type,
        confidence=result.get("confidence", 0.0),
        model=result.get("model", ""),
    )

    return SuggestResponse(
        response=result["response"],
        alternatives=result.get("alternatives", []),
        confidence=result.get("confidence", 0.0),
        person_type=req.person_type,
        model=result.get("model", ""),
        response_id=response_id,
    )


@app.post("/feedback", tags=["twin"])
def submit_feedback(req: FeedbackRequest):
    """Soumettre un feedback sur une réponse générée (améliore le profil)."""
    store.rate_response(req.response_id, req.rating, req.used)
    return {"status": "ok", "response_id": req.response_id, "rating": req.rating}


# ── /train ────────────────────────────────────────────────────

@app.post("/train", response_model=TrainResponse, tags=["training"])
def retrain():
    """
    Réentraîne le profil sur tous les messages importés en DB.
    Utile après avoir importé de nouveaux fichiers.
    """
    before = engine.get_profile().total_messages_analyzed
    before_version = engine.get_profile().version

    # Récupérer tous mes messages de la DB
    all_my_msgs = store.get_my_messages(limit=10000)

    if not all_my_msgs:
        raise HTTPException(
            status_code=428,
            detail="Aucun message en base. Importe d'abord des conversations.",
        )

    # Réinitialiser et réentraîner
    engine.reset()
    by_source: dict = {}
    for msg in all_my_msgs:
        src = msg.get("source", "unknown")
        by_source.setdefault(src, []).append(msg)

    for src, msgs in by_source.items():
        engine.ingest(msgs, source=src)

    after = engine.get_profile().total_messages_analyzed

    # Snapshot en DB
    store.save_personality_snapshot(engine.get_profile().to_dict(), engine.get_profile().version)
    store.log_event("retrain", {"messages": after, "sources": list(by_source.keys())})

    return TrainResponse(
        status="success",
        messages_before=before,
        messages_after=after,
        profile_version=engine.get_profile().version,
    )


# ── /stats ────────────────────────────────────────────────────

@app.get("/stats", tags=["stats"])
def get_stats():
    """Statistiques complètes d'apprentissage."""
    db_stats = store.get_stats()
    profile = engine.get_profile()
    return {
        **db_stats,
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "last_updated": profile.last_updated,
            "dominant_tone": profile.dominant_tone,
            "avg_message_length": profile.avg_message_length,
            "emoji_usage_rate": profile.emoji_usage_rate,
            "top_emojis": profile.top_emojis[:5],
            "sources": profile.sources,
        },
    }


# ── /contacts ─────────────────────────────────────────────────

@app.get("/contacts", tags=["contacts"])
def list_contacts():
    """Liste les contacts connus."""
    return {"contacts": store.list_contacts()}


@app.post("/contacts", tags=["contacts"])
def add_contact(req: ContactRequest):
    """Ajoute ou met à jour un contact avec son type."""
    store.upsert_contact(
        name=req.name,
        person_type=req.person_type,
        platform=req.platform,
        notes=req.notes,
    )
    return {"status": "ok", "contact": req.name, "type": req.person_type}


# ── /history ──────────────────────────────────────────────────

@app.get("/history", tags=["twin"])
def get_history(limit: int = 20):
    """Historique des dernières réponses générées."""
    return {"responses": store.get_recent_responses(limit=limit)}


@app.get("/events", tags=["stats"])
def get_events(limit: int = 20):
    """Journal des événements système."""
    return {"events": store.get_events(limit=limit)}


# ── /wa/* — Proxy vers le bridge WhatsApp local ───────────────

WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://localhost:3001")

@app.api_route("/wa/{path:path}", methods=["GET", "POST", "OPTIONS", "DELETE"], tags=["bridge"])
async def wa_proxy(path: str, request: Request):
    """
    Proxy transparent vers le bridge WhatsApp (localhost:3001).
    Le frontend n'a besoin que de l'URL du backend — plus de VITE_WA_BRIDGE_URL.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{WA_BRIDGE_URL}/{path}"
        body = await request.body()
        params = dict(request.query_params)
        headers = {}
        if body:
            headers["Content-Type"] = "application/json"
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                content=body,
                params=params,
                headers=headers,
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json"),
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            # Bridge pas encore démarré ou hors ligne
            return Response(
                content='{"status":"bridge_offline","connected":false,"chats":0,"messages":0,"historySyncDone":false}',
                status_code=200,
                media_type="application/json",
            )


# ── /conversations ────────────────────────────────────────────

@app.get("/conversations", tags=["conversations"])
def list_imported_conversations():
    """Liste toutes les conversations importées (fichiers dans raw_conversations)."""
    convs = []
    for f in sorted(RAW_DIR.iterdir()):
        if f.suffix.lower() not in (".txt", ".json"):
            continue
        try:
            size = f.stat().st_size
            # Compter les messages sans tout parser
            count = 0
            if f.suffix.lower() == ".txt":
                import re as _re
                pat = _re.compile(r"^\[?\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}")
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    count = sum(1 for line in fh if pat.match(line))
            elif f.suffix.lower() == ".json":
                import json as _json
                with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                    data = _json.load(fh)
                count = len(data.get("messages", []))
            convs.append({
                "name": f.stem,
                "filename": f.name,
                "size_kb": round(size / 1024, 1),
                "message_count": count,
            })
        except Exception:
            convs.append({"name": f.stem, "filename": f.name, "size_kb": 0, "message_count": 0})
    return {"conversations": convs, "total": len(convs)}


@app.get("/conversations/{name}", tags=["conversations"])
def get_imported_conversation(name: str, limit: int = 200, offset: int = 0):
    """Retourne les messages d'une conversation importée."""
    # Chercher le fichier (avec ou sans extension)
    found = None
    for ext in (".txt", ".json"):
        candidate = RAW_DIR / (name + ext)
        if candidate.exists():
            found = candidate
            break
    # Essai direct (nom avec extension)
    if not found:
        candidate = RAW_DIR / name
        if candidate.exists():
            found = candidate

    if not found:
        raise HTTPException(status_code=404, detail=f"Conversation '{name}' introuvable")

    ext = found.suffix.lower()
    try:
        if ext == ".txt":
            parser = WhatsAppParser()
        elif ext == ".json":
            # Détecter Telegram vs Instagram
            import json as _json
            with open(found, "r", encoding="utf-8", errors="ignore") as fh:
                sample = _json.load(fh)
            if "messages" in sample and sample.get("messages") and "sender_name" in (sample["messages"][0] if sample["messages"] else {}):
                parser = InstagramParser()
            else:
                parser = TelegramParser()
        else:
            raise HTTPException(status_code=400, detail="Format non supporté")

        _, all_msgs = parser.parse(found, MY_NAME)
        all_msgs_dicts = [m.to_dict() for m in all_msgs]
        # Marquer mes messages
        for m in all_msgs_dicts:
            m["is_mine"] = m["sender"].lower() == MY_NAME.lower()

        total = len(all_msgs_dicts)
        page = all_msgs_dicts[offset: offset + limit]

        return {
            "name": name,
            "total": total,
            "offset": offset,
            "limit": limit,
            "messages": page,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lecture : {e}")


# ─────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"\n🤖 Digital Twin AI — {MY_NAME}")
    print(f"📊 Messages analysés : {engine.get_profile().total_messages_analyzed}")
    print(f"🚀 Démarrage sur http://localhost:8000\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
