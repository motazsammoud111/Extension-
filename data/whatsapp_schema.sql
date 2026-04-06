-- ============================================================
-- Tables Supabase pour le stockage WhatsApp (Digital Twin AI)
-- Execute ce SQL dans Supabase > SQL Editor
-- ============================================================

-- Table des chats WhatsApp
CREATE TABLE IF NOT EXISTS whatsapp_chats (
  chat_id       TEXT PRIMARY KEY,
  name          TEXT NOT NULL DEFAULT '',
  last_message  TEXT DEFAULT '',
  timestamp     BIGINT DEFAULT 0,
  unread_count  INT DEFAULT 0,
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Table des messages WhatsApp
CREATE TABLE IF NOT EXISTS whatsapp_messages (
  message_id  TEXT PRIMARY KEY,
  chat_id     TEXT NOT NULL REFERENCES whatsapp_chats(chat_id) ON DELETE CASCADE,
  body        TEXT DEFAULT '',
  from_me     BOOLEAN DEFAULT FALSE,
  push_name   TEXT DEFAULT '',
  media_type  TEXT,
  timestamp   BIGINT DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index pour accelerer les requetes
CREATE INDEX IF NOT EXISTS idx_wa_messages_chat_id   ON whatsapp_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_wa_messages_timestamp ON whatsapp_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_wa_chats_timestamp    ON whatsapp_chats(timestamp DESC);

-- Desactiver RLS (le bridge utilise la service key)
ALTER TABLE whatsapp_chats    DISABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_messages DISABLE ROW LEVEL SECURITY;

-- Stats rapides
CREATE OR REPLACE VIEW whatsapp_stats AS
SELECT
  COUNT(DISTINCT chat_id)                        AS total_chats,
  COUNT(*)                                       AS total_messages,
  COUNT(*) FILTER (WHERE from_me = true)         AS my_messages,
  COUNT(*) FILTER (WHERE from_me = false)        AS received_messages,
  MIN(timestamp)                                 AS oldest_message,
  MAX(timestamp)                                 AS newest_message
FROM whatsapp_messages;
