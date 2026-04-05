"""
main.py — API FastAPI du Digital Twin AI
Endpoints : /import, /personality, /suggest, /train, /stats
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent))

from personality_engine import PersonalityEngine
from conversation_analyzer import ConversationAnalyzer
from response_generator import ResponseGenerator
from memory_store import MemoryStore


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

MY_NAME = os.getenv("MY_NAME", "Motaz")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

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
# Services
# ─────────────────────────────────────────────────────────────

engine   = PersonalityEngine(profile_path=PROF_PATH)
analyzer = ConversationAnalyzer(my_name=MY_NAME, engine=engine)
generator = ResponseGenerator(engine=engine, api_key=GROQ_API_KEY)
store    = MemoryStore(db_path=str(DB_PATH))


# ─────────────────────────────────────────────────────────────
# App FastAPI
# ─────────────────────────────────────────────────────────────

app = FastAPI(title="Digital Twin AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────

class SuggestRequest(BaseModel):
    message: str
    person_type: str = "close_friend"
    context_note: str = ""
    history: Optional[List[dict]] = None

class SuggestResponse(BaseModel):
    response: str
    alternatives: List[str]
    confidence: float
    person_type: str
    model: str
    response_id: Optional[int] = None

class FeedbackRequest(BaseModel):
    response_id: int
    rating: int = Field(..., ge=-1, le=1)
    used: bool = False

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

@app.get("/")
def root():
    return {
        "twin": MY_NAME,
        "status": "online",
        "messages_analyzed": engine.get_profile().total_messages_analyzed,
        "profile_version": engine.get_profile().version,
    }

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/import", response_model=ImportResponse)
async def import_conversation(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".txt", ".json"):
        raise HTTPException(400, "Format non supporté. Utilise .txt ou .json.")

    dest = RAW_DIR / file.filename
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        report = analyzer.analyze_file(dest)
    except Exception as e:
        raise HTTPException(500, f"Erreur d'analyse : {e}")

    if "error" in report:
        raise HTTPException(422, detail=report["error"])

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


@app.get("/personality")
def get_personality():
    return engine.get_profile().to_dict()

@app.get("/personality/summary")
def get_personality_summary():
    return {"summary": engine.get_profile().summary()}

@app.get("/personality/prompt-preview")
def get_prompt_preview(person_type: str = "close_friend"):
    return {"system_prompt": generator.build_system_prompt_preview(person_type)}


@app.post("/suggest", response_model=SuggestResponse)
def suggest_response(req: SuggestRequest):
    profile = engine.get_profile()
    if profile.total_messages_analyzed == 0:
        raise HTTPException(428, detail="Aucun profil chargé. Importe d'abord des conversations.")
    if not GROQ_API_KEY:
        raise HTTPException(503, detail="GROQ_API_KEY non configurée.")

    result = generator.suggest(
        incoming_message=req.message,
        conversation_history=req.history,
        person_type=req.person_type,
        context_note=req.context_note,
    )
    if "error" in result:
        raise HTTPException(502, detail=result["error"])

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


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    store.rate_response(req.response_id, req.rating, req.used)
    return {"status": "ok"}


@app.post("/train", response_model=TrainResponse)
def retrain():
    before = engine.get_profile().total_messages_analyzed
    all_my_msgs = store.get_my_messages(limit=10000)
    if not all_my_msgs:
        raise HTTPException(428, detail="Aucun message en base. Importe d'abord des conversations.")
    engine.reset()
    by_source = {}
    for msg in all_my_msgs:
        src = msg.get("source", "unknown")
        by_source.setdefault(src, []).append(msg)
    for src, msgs in by_source.items():
        engine.ingest(msgs, source=src)
    after = engine.get_profile().total_messages_analyzed
    store.save_personality_snapshot(engine.get_profile().to_dict(), engine.get_profile().version)
    store.log_event("retrain", {"messages": after, "sources": list(by_source.keys())})
    return TrainResponse(
        status="success",
        messages_before=before,
        messages_after=after,
        profile_version=engine.get_profile().version,
    )


@app.get("/stats")
def get_stats():
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


@app.get("/contacts")
def list_contacts():
    return {"contacts": store.list_contacts()}

@app.post("/contacts")
def add_contact(req: ContactRequest):
    store.upsert_contact(req.name, req.person_type, req.platform, req.notes)
    return {"status": "ok"}


@app.get("/history")
def get_history(limit: int = 20):
    return {"responses": store.get_recent_responses(limit=limit)}

@app.get("/events")
def get_events(limit: int = 20):
    return {"events": store.get_events(limit=limit)}


# ─────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"\n🤖 Digital Twin AI — {MY_NAME}")
    print(f"📊 Messages analysés : {engine.get_profile().total_messages_analyzed}")
    print(f"🚀 Démarrage sur http://localhost:8000\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)