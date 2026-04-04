-- ═══════════════════════════════════════════════════════════════
-- Digital Twin AI — Schéma Supabase
-- Colle ce SQL dans : Supabase Dashboard → SQL Editor → Run
-- ═══════════════════════════════════════════════════════════════

-- Messages importés depuis les sources
CREATE TABLE IF NOT EXISTS messages (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    sender          TEXT NOT NULL,
    text            TEXT NOT NULL,
    timestamp       TEXT,
    is_mine         BOOLEAN DEFAULT FALSE,
    conversation_id TEXT,
    imported_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, sender, text, timestamp)
);

-- Réponses générées par le twin
CREATE TABLE IF NOT EXISTS generated_responses (
    id           BIGSERIAL PRIMARY KEY,
    incoming_msg TEXT NOT NULL,
    response     TEXT NOT NULL,
    alternatives JSONB DEFAULT '[]',
    person_type  TEXT DEFAULT 'close_friend',
    confidence   FLOAT DEFAULT 0.0,
    model        TEXT,
    used         BOOLEAN DEFAULT FALSE,
    rating       SMALLINT,                     -- -1 | 0 | 1
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Profil de personnalité versionné
CREATE TABLE IF NOT EXISTS personality_snapshots (
    id         BIGSERIAL PRIMARY KEY,
    version    INTEGER NOT NULL,
    profile    JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contacts connus
CREATE TABLE IF NOT EXISTS contacts (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    person_type TEXT DEFAULT 'unknown',
    platform    TEXT,
    notes       TEXT,
    last_seen   TIMESTAMPTZ DEFAULT NOW(),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Journal des événements
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    details    JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index pour performance
CREATE INDEX IF NOT EXISTS idx_messages_source  ON messages(source);
CREATE INDEX IF NOT EXISTS idx_messages_is_mine ON messages(is_mine);
CREATE INDEX IF NOT EXISTS idx_messages_sender  ON messages(sender);
CREATE INDEX IF NOT EXISTS idx_responses_created ON generated_responses(created_at DESC);

-- Row Level Security (désactivé pour l'usage personnel)
ALTER TABLE messages              DISABLE ROW LEVEL SECURITY;
ALTER TABLE generated_responses   DISABLE ROW LEVEL SECURITY;
ALTER TABLE personality_snapshots DISABLE ROW LEVEL SECURITY;
ALTER TABLE contacts              DISABLE ROW LEVEL SECURITY;
ALTER TABLE events                DISABLE ROW LEVEL SECURITY;
