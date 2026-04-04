"""
memory_store.py — Mémoire long terme du Digital Twin
Supporte Supabase (production) et SQLite (fallback local).
→ Si SUPABASE_URL et SUPABASE_KEY sont dans .env → Supabase
→ Sinon → SQLite local
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Schéma SQLite (fallback local)
# ─────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    sender          TEXT NOT NULL,
    text            TEXT NOT NULL,
    timestamp       TEXT,
    is_mine         INTEGER DEFAULT 0,
    conversation_id TEXT,
    imported_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(source, sender, text, timestamp)
);
CREATE TABLE IF NOT EXISTS generated_responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incoming_msg TEXT NOT NULL,
    response     TEXT NOT NULL,
    alternatives TEXT,
    person_type  TEXT DEFAULT 'close_friend',
    confidence   REAL DEFAULT 0.0,
    model        TEXT,
    used         INTEGER DEFAULT 0,
    rating       INTEGER,
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS personality_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version    INTEGER NOT NULL,
    profile    TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    person_type TEXT DEFAULT 'unknown',
    platform    TEXT,
    notes       TEXT,
    last_seen   TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    details    TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_source  ON messages(source);
CREATE INDEX IF NOT EXISTS idx_messages_is_mine ON messages(is_mine);
CREATE INDEX IF NOT EXISTS idx_messages_sender  ON messages(sender);
"""


# ─────────────────────────────────────────────────────────────
# MemoryStore — abstraction Supabase / SQLite
# ─────────────────────────────────────────────────────────────

class MemoryStore:
    """
    Interface de stockage unifiée.
    Détecte automatiquement Supabase si les variables sont présentes,
    sinon utilise SQLite en local.
    """

    def __init__(self, db_path: str = "data/memory.db"):
        self.supabase_url = os.getenv("SUPABASE_URL", "")
        self.supabase_key = os.getenv("SUPABASE_KEY", "")
        self.use_supabase = bool(self.supabase_url and self.supabase_key)

        if self.use_supabase:
            self._init_supabase()
            print(f"☁️  Supabase connecté : {self.supabase_url[:40]}...")
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()
            print(f"💾 SQLite local : {self.db_path}")

    # ── Init ───────────────────────────────────────────────

    def _init_supabase(self):
        try:
            from supabase import create_client
            self._sb = create_client(self.supabase_url, self.supabase_key)
        except ImportError:
            print("⚠️  supabase-py non installé. Fallback SQLite.")
            print("   pip install supabase")
            self.use_supabase = False
            self.db_path = Path("data/memory.db")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()

    def _init_sqlite(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ── SQLite helpers ─────────────────────────────────────

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────
    # Messages
    # ─────────────────────────────────────────────────────

    def save_messages(self, messages: List[dict], my_name: str) -> int:
        inserted = 0
        rows = []
        for m in messages:
            row = {
                "source": m.get("source", ""),
                "sender": m.get("sender", ""),
                "text": m.get("text", ""),
                "timestamp": m.get("timestamp", ""),
                "is_mine": m.get("sender", "").lower() == my_name.lower(),
                "conversation_id": m.get("conversation_id", ""),
            }
            rows.append(row)

        if self.use_supabase:
            try:
                # upsert → ignore doublons
                res = self._sb.table("messages").upsert(
                    rows,
                    on_conflict="source,sender,text,timestamp",
                    ignore_duplicates=True,
                ).execute()
                inserted = len(res.data) if res.data else 0
            except Exception as e:
                print(f"⚠️  Supabase save_messages error: {e}")
        else:
            with self._conn() as conn:
                for row in rows:
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO messages "
                            "(source,sender,text,timestamp,is_mine,conversation_id) "
                            "VALUES (?,?,?,?,?,?)",
                            (row["source"], row["sender"], row["text"],
                             row["timestamp"], int(row["is_mine"]), row["conversation_id"]),
                        )
                        if conn.execute("SELECT changes()").fetchone()[0]:
                            inserted += 1
                    except sqlite3.Error:
                        pass
        return inserted

    def get_my_messages(self, source: Optional[str] = None, limit: int = 500) -> List[dict]:
        if self.use_supabase:
            try:
                q = self._sb.table("messages").select("*").eq("is_mine", True)
                if source:
                    q = q.eq("source", source)
                res = q.order("timestamp", desc=True).limit(limit).execute()
                return res.data or []
            except Exception as e:
                print(f"⚠️  Supabase get_my_messages error: {e}")
                return []
        else:
            query = "SELECT * FROM messages WHERE is_mine=1"
            params: list = []
            if source:
                query += " AND source=?"
                params.append(source)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            with self._conn() as conn:
                rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def message_count(self, source: Optional[str] = None) -> int:
        if self.use_supabase:
            try:
                q = self._sb.table("messages").select("id", count="exact").eq("is_mine", True)
                if source:
                    q = q.eq("source", source)
                return q.execute().count or 0
            except Exception:
                return 0
        else:
            query = "SELECT COUNT(*) FROM messages WHERE is_mine=1"
            params = []
            if source:
                query += " AND source=?"
                params.append(source)
            with self._conn() as conn:
                return conn.execute(query, params).fetchone()[0]

    # ─────────────────────────────────────────────────────
    # Réponses générées
    # ─────────────────────────────────────────────────────

    def save_response(self, incoming: str, response: str, alternatives: List[str],
                      person_type: str, confidence: float, model: str) -> int:
        row = {
            "incoming_msg": incoming,
            "response": response,
            "alternatives": alternatives,
            "person_type": person_type,
            "confidence": confidence,
            "model": model,
        }
        if self.use_supabase:
            try:
                res = self._sb.table("generated_responses").insert(row).execute()
                return res.data[0]["id"] if res.data else 0
            except Exception as e:
                print(f"⚠️  Supabase save_response error: {e}")
                return 0
        else:
            row["alternatives"] = json.dumps(alternatives, ensure_ascii=False)
            with self._conn() as conn:
                cursor = conn.execute(
                    "INSERT INTO generated_responses "
                    "(incoming_msg,response,alternatives,person_type,confidence,model) "
                    "VALUES (?,?,?,?,?,?)",
                    (incoming, response, row["alternatives"], person_type, confidence, model),
                )
            return cursor.lastrowid

    def rate_response(self, response_id: int, rating: int, used: bool = False):
        if self.use_supabase:
            try:
                self._sb.table("generated_responses").update(
                    {"rating": rating, "used": used}
                ).eq("id", response_id).execute()
            except Exception as e:
                print(f"⚠️  Supabase rate_response error: {e}")
        else:
            with self._conn() as conn:
                conn.execute(
                    "UPDATE generated_responses SET rating=?,used=? WHERE id=?",
                    (rating, int(used), response_id),
                )

    def get_recent_responses(self, limit: int = 10) -> List[dict]:
        if self.use_supabase:
            try:
                res = self._sb.table("generated_responses")\
                    .select("*").order("created_at", desc=True).limit(limit).execute()
                return res.data or []
            except Exception:
                return []
        else:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM generated_responses ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["alternatives"] = json.loads(d.get("alternatives") or "[]")
                results.append(d)
            return results

    # ─────────────────────────────────────────────────────
    # Profil
    # ─────────────────────────────────────────────────────

    def save_personality_snapshot(self, profile_dict: dict, version: int):
        if self.use_supabase:
            try:
                self._sb.table("personality_snapshots").insert(
                    {"version": version, "profile": profile_dict}
                ).execute()
            except Exception as e:
                print(f"⚠️  Supabase snapshot error: {e}")
        else:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO personality_snapshots (version,profile) VALUES (?,?)",
                    (version, json.dumps(profile_dict, ensure_ascii=False)),
                )

    def get_latest_snapshot(self) -> Optional[dict]:
        if self.use_supabase:
            try:
                res = self._sb.table("personality_snapshots")\
                    .select("profile").order("version", desc=True).limit(1).execute()
                return res.data[0]["profile"] if res.data else None
            except Exception:
                return None
        else:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT profile FROM personality_snapshots ORDER BY version DESC LIMIT 1"
                ).fetchone()
            return json.loads(row["profile"]) if row else None

    # ─────────────────────────────────────────────────────
    # Contacts
    # ─────────────────────────────────────────────────────

    def upsert_contact(self, name: str, person_type: str = "unknown",
                       platform: str = "", notes: str = ""):
        row = {"name": name, "person_type": person_type,
               "platform": platform, "notes": notes,
               "last_seen": datetime.now().isoformat()}
        if self.use_supabase:
            try:
                self._sb.table("contacts").upsert(row, on_conflict="name").execute()
            except Exception as e:
                print(f"⚠️  Supabase upsert_contact error: {e}")
        else:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO contacts (name,person_type,platform,notes,last_seen) "
                    "VALUES (?,?,?,?,datetime('now')) "
                    "ON CONFLICT(name) DO UPDATE SET "
                    "person_type=excluded.person_type, platform=excluded.platform, "
                    "notes=excluded.notes, last_seen=datetime('now')",
                    (name, person_type, platform, notes),
                )

    def get_contact(self, name: str) -> Optional[dict]:
        if self.use_supabase:
            try:
                res = self._sb.table("contacts").select("*").eq("name", name).execute()
                return res.data[0] if res.data else None
            except Exception:
                return None
        else:
            with self._conn() as conn:
                row = conn.execute("SELECT * FROM contacts WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None

    def list_contacts(self) -> List[dict]:
        if self.use_supabase:
            try:
                res = self._sb.table("contacts").select("*")\
                    .order("last_seen", desc=True).execute()
                return res.data or []
            except Exception:
                return []
        else:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM contacts ORDER BY last_seen DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────
    # Événements
    # ─────────────────────────────────────────────────────

    def log_event(self, event_type: str, details: Optional[dict] = None):
        if self.use_supabase:
            try:
                self._sb.table("events").insert(
                    {"event_type": event_type, "details": details or {}}
                ).execute()
            except Exception:
                pass
        else:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO events (event_type,details) VALUES (?,?)",
                    (event_type, json.dumps(details or {}, ensure_ascii=False)),
                )

    def get_events(self, limit: int = 20) -> List[dict]:
        if self.use_supabase:
            try:
                res = self._sb.table("events").select("*")\
                    .order("created_at", desc=True).limit(limit).execute()
                return res.data or []
            except Exception:
                return []
        else:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        if self.use_supabase:
            try:
                total = self._sb.table("messages").select("id", count="exact")\
                    .eq("is_mine", True).execute().count or 0

                by_src_res = self._sb.table("messages").select("source")\
                    .eq("is_mine", True).execute()
                by_source: dict = {}
                for r in (by_src_res.data or []):
                    by_source[r["source"]] = by_source.get(r["source"], 0) + 1

                gen = self._sb.table("generated_responses").select("id", count="exact").execute().count or 0
                used = self._sb.table("generated_responses").select("id", count="exact")\
                    .eq("used", True).execute().count or 0
                conf_res = self._sb.table("generated_responses").select("confidence").execute()
                confs = [r["confidence"] for r in (conf_res.data or []) if r.get("confidence")]
                avg_conf = sum(confs) / len(confs) if confs else 0.0

                ratings_res = self._sb.table("generated_responses")\
                    .select("rating").not_.is_("rating", "null").execute()
                ratings = {"good": 0, "bad": 0, "neutral": 0}
                for r in (ratings_res.data or []):
                    if r["rating"] == 1: ratings["good"] += 1
                    elif r["rating"] == -1: ratings["bad"] += 1
                    else: ratings["neutral"] += 1

                contacts = self._sb.table("contacts").select("id", count="exact").execute().count or 0
                snapshots = self._sb.table("personality_snapshots").select("id", count="exact").execute().count or 0

                return {
                    "messages_analyzed": total,
                    "messages_by_source": by_source,
                    "responses_generated": gen,
                    "responses_used": used,
                    "avg_confidence": round(avg_conf, 3),
                    "ratings": ratings,
                    "contacts": contacts,
                    "personality_versions": snapshots,
                    "storage": "supabase",
                }
            except Exception as e:
                print(f"⚠️  Supabase stats error: {e}")
                return {"storage": "supabase", "error": str(e)}
        else:
            with self._conn() as conn:
                total = conn.execute("SELECT COUNT(*) FROM messages WHERE is_mine=1").fetchone()[0]
                by_source = {
                    r["source"]: r["cnt"]
                    for r in conn.execute(
                        "SELECT source, COUNT(*) AS cnt FROM messages WHERE is_mine=1 GROUP BY source"
                    ).fetchall()
                }
                gen = conn.execute("SELECT COUNT(*) FROM generated_responses").fetchone()[0]
                used = conn.execute("SELECT COUNT(*) FROM generated_responses WHERE used=1").fetchone()[0]
                avg_conf = conn.execute("SELECT AVG(confidence) FROM generated_responses").fetchone()[0] or 0.0
                r = conn.execute(
                    "SELECT SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) good, "
                    "SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) bad, "
                    "SUM(CASE WHEN rating=0 THEN 1 ELSE 0 END) neutral "
                    "FROM generated_responses WHERE rating IS NOT NULL"
                ).fetchone()
                contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
                snapshots = conn.execute("SELECT COUNT(*) FROM personality_snapshots").fetchone()[0]

            return {
                "messages_analyzed": total,
                "messages_by_source": by_source,
                "responses_generated": gen,
                "responses_used": used,
                "avg_confidence": round(avg_conf, 3),
                "ratings": {"good": r["good"] or 0, "bad": r["bad"] or 0, "neutral": r["neutral"] or 0},
                "contacts": contacts,
                "personality_versions": snapshots,
                "storage": "sqlite",
            }

    def export_my_messages(self, output_path: Path, source: Optional[str] = None):
        msgs = self.get_my_messages(source=source, limit=10000)
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            for m in msgs:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
        print(f"📤 {len(msgs)} messages exportés vers {output_path}")
