/**
 * whatsapp-bridge/index.js — version cloud (Railway)
 * - Sauvegarde TOUTES les messages dans Supabase (persistance 24/7)
 * - messaging-history.set pour historique complet
 * - Auth stocke dans AUTH_DIR (volume Railway ou local)
 */

import 'dotenv/config'
import express from 'express'
import QRCode from 'qrcode'
import pino from 'pino'
import { existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { createClient } from '@supabase/supabase-js'

const __dirname = dirname(fileURLToPath(import.meta.url))

const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = await import('@whiskeysockets/baileys')

// ─────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────
const PORT      = process.env.PORT || process.env.WA_BRIDGE_PORT || 3001
const AUTH_DIR  = process.env.AUTH_DIR || join(__dirname, '.wa_auth')
const TWIN_API  = process.env.TWIN_API_URL || 'https://digital-twin-backend-9z0t.onrender.com'

// Supabase
const SUPABASE_URL = process.env.SUPABASE_URL || ''
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_KEY || ''

let supabase = null
if (SUPABASE_URL && SUPABASE_KEY) {
  supabase = createClient(SUPABASE_URL, SUPABASE_KEY)
  console.log('✅ Supabase connecte')
} else {
  console.log('⚠️  Supabase non configure — les messages seront seulement en memoire')
}

if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })

// ─────────────────────────────────────────────────────────
// Etat global (cache memoire rapide)
// ─────────────────────────────────────────────────────────
let sock             = null
let qrDataUrl        = null
let connectionStatus = 'disconnected'
let historySyncDone  = false

const messageCache = new Map()   // chatId → [msg, ...]  (derniers 100 msgs)
const chatList     = new Map()   // chatId → metadata

// ─────────────────────────────────────────────────────────
// Express
// ─────────────────────────────────────────────────────────
const app = express()

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  res.setHeader('Access-Control-Allow-Private-Network', 'true')
  if (req.method === 'OPTIONS') return res.sendStatus(200)
  next()
})
app.use(express.json())

// ─────────────────────────────────────────────────────────
// API REST
// ─────────────────────────────────────────────────────────
app.get('/', (req, res) => res.json({ service: 'Digital Twin WhatsApp Bridge', status: connectionStatus }))

app.get('/health', (req, res) => res.json({ status: 'ok' }))

app.get('/status', (req, res) => {
  const totalMsgs = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)
  res.json({
    status: connectionStatus,
    qr: qrDataUrl,
    connected: connectionStatus === 'connected',
    chats: chatList.size,
    messages: totalMsgs,
    historySyncDone,
    supabase: !!supabase,
  })
})

app.post('/connect', async (req, res) => {
  if (connectionStatus === 'connected') return res.json({ message: 'Deja connecte' })
  await startWhatsApp()
  res.json({ message: 'Connexion initiee' })
})

app.post('/disconnect', async (req, res) => {
  if (sock) await sock.logout()
  sock = null
  connectionStatus = 'disconnected'
  qrDataUrl = null
  res.json({ message: 'Deconnecte' })
})

// Liste chats (depuis Supabase si disponible, sinon memoire)
app.get('/chats', async (req, res) => {
  let chats = []

  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('whatsapp_chats')
        .select('*')
        .order('timestamp', { ascending: false })
        .limit(100)
      if (!error && data) {
        chats = data.map(c => ({
          id: c.chat_id,
          name: c.name,
          lastMessage: c.last_message,
          timestamp: c.timestamp,
          unreadCount: c.unread_count || 0,
        }))
      }
    } catch {}
  }

  // Fallback memoire
  if (!chats.length) {
    chats = Array.from(chatList.entries())
      .map(([id, meta]) => ({ id, ...meta }))
      .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
      .slice(0, 100)
  }

  res.json({ chats, total: chats.length, syncDone: historySyncDone })
})

// Messages d'un chat (depuis Supabase si disponible)
app.get('/messages/:chatId', async (req, res) => {
  const chatId = req.params.chatId
  let messages = []

  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('whatsapp_messages')
        .select('*')
        .eq('chat_id', chatId)
        .order('timestamp', { ascending: true })
        .limit(200)
      if (!error && data) {
        messages = data.map(m => ({
          id: m.message_id,
          fromMe: m.from_me,
          body: m.body,
          timestamp: m.timestamp,
          pushName: m.push_name,
          mediaType: m.media_type,
        }))
      }
    } catch {}
  }

  // Fallback memoire
  if (!messages.length) {
    const cached = messageCache.get(chatId) || []
    messages = [...cached].sort((a, b) => (Number(a.timestamp) || 0) - (Number(b.timestamp) || 0))
  }

  res.json({ messages })
})

// Envoyer un message
app.post('/send', async (req, res) => {
  const { chatId, message } = req.body
  if (!sock || connectionStatus !== 'connected')
    return res.status(503).json({ error: 'Non connecte' })
  try {
    await sock.sendMessage(chatId, { text: message })
    const newMsg = {
      id: Date.now().toString(),
      fromMe: true,
      body: message,
      timestamp: Math.floor(Date.now() / 1000),
    }
    await saveMessage(chatId, newMsg, '')
    res.json({ success: true })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// Suggestion IA
app.post('/suggest', async (req, res) => {
  const { message, person_type = 'close_friend' } = req.body
  try {
    const response = await fetch(`${TWIN_API}/suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, person_type }),
    })
    const data = await response.json()
    res.json(data)
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// ─────────────────────────────────────────────────────────
// Supabase — sauvegarde
// ─────────────────────────────────────────────────────────
async function saveMessage(chatId, msg, pushName) {
  // Memoire locale
  if (!messageCache.has(chatId)) messageCache.set(chatId, [])
  const arr = messageCache.get(chatId)
  if (!arr.find(m => m.id === msg.id)) {
    arr.push(msg)
    if (arr.length > 200) arr.shift()
  }

  // Supabase
  if (!supabase) return
  try {
    await supabase.from('whatsapp_messages').upsert({
      message_id: msg.id,
      chat_id: chatId,
      body: msg.body || '',
      from_me: msg.fromMe,
      push_name: pushName || msg.pushName || '',
      media_type: msg.mediaType || null,
      timestamp: Number(msg.timestamp) || 0,
    }, { onConflict: 'message_id' })
  } catch (err) {
    // Silencieux — ne pas bloquer le flux
  }
}

async function saveChat(chatId, meta) {
  // Memoire locale
  chatList.set(chatId, meta)

  // Supabase
  if (!supabase) return
  try {
    await supabase.from('whatsapp_chats').upsert({
      chat_id: chatId,
      name: meta.name || chatId.split('@')[0],
      last_message: meta.lastMessage || '',
      timestamp: Number(meta.timestamp) || 0,
      unread_count: meta.unreadCount || 0,
      updated_at: new Date().toISOString(),
    }, { onConflict: 'chat_id' })
  } catch {}
}

// ─────────────────────────────────────────────────────────
// Utilitaires
// ─────────────────────────────────────────────────────────
function formatMessage(msg) {
  let body = '', mediaType = null

  if (msg.message?.conversation)
    body = msg.message.conversation
  else if (msg.message?.extendedTextMessage?.text)
    body = msg.message.extendedTextMessage.text
  else if (msg.message?.imageMessage) {
    mediaType = 'image'
    body = msg.message.imageMessage.caption ? `📷 ${msg.message.imageMessage.caption}` : '📷 Image'
  } else if (msg.message?.videoMessage) {
    mediaType = 'video'
    body = msg.message.videoMessage.caption ? `🎥 ${msg.message.videoMessage.caption}` : '🎥 Video'
  } else if (msg.message?.documentMessage) {
    mediaType = 'document'
    body = `📄 ${msg.message.documentMessage.fileName || 'Document'}`
  } else if (msg.message?.audioMessage) {
    mediaType = 'audio'; body = '🎵 Message vocal'
  } else if (msg.message?.stickerMessage) {
    mediaType = 'sticker'; body = '🖼️ Sticker'
  } else if (msg.message?.reactionMessage)
    body = `${msg.message.reactionMessage.text || '👍'} (reaction)`
  else if (msg.message?.locationMessage)
    body = '📍 Localisation'
  else
    body = '[Media]'

  return {
    id: msg.key?.id || String(Date.now()),
    fromMe: !!msg.key?.fromMe,
    body,
    timestamp: msg.messageTimestamp,
    pushName: msg.pushName || '',
    mediaType,
  }
}

// Ingerer un batch de messages (historique ou temps reel)
async function ingestBatch(waMsgs) {
  if (!waMsgs?.length) return 0
  let count = 0
  // Pour ne pas saturer Supabase, on traite par lots de 50
  for (let i = 0; i < waMsgs.length; i += 50) {
    const batch = waMsgs.slice(i, i + 50)
    await Promise.all(batch.map(async (msg) => {
      if (!msg?.message) return
      const chatId = msg.key?.remoteJid
      if (!chatId) return
      const formatted = formatMessage(msg)
      await saveMessage(chatId, formatted, msg.pushName || '')
      count++
    }))
  }
  return count
}

// ─────────────────────────────────────────────────────────
// Connexion WhatsApp
// ─────────────────────────────────────────────────────────
async function startWhatsApp() {
  if (sock) return

  const logger = pino({ level: 'silent' })
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()

  console.log(`\n🟢 Baileys v${version.join('.')} — Connexion WhatsApp...`)

  sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    printQRInTerminal: false,
    logger,
    syncFullHistory: true,
    markOnlineOnConnect: false,
  })

  sock.ev.on('creds.update', saveCreds)

  // ── QR / Connexion ──────────────────────────────────────
  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      connectionStatus = 'qr'
      qrDataUrl = await QRCode.toDataURL(qr)
      console.log('📱 QR code genere — scanne dans le frontend')
    }

    if (connection === 'open') {
      connectionStatus = 'connected'
      qrDataUrl = null
      historySyncDone = false
      console.log('✅ WhatsApp connecte ! Attente sync historique...')
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      const shouldReconnect = code !== DisconnectReason.loggedOut
      console.log(`❌ Deconnecte (code ${code}) — ${shouldReconnect ? 'reconnexion dans 5s...' : 'logout definitif'}`)
      sock = null
      connectionStatus = 'disconnected'
      qrDataUrl = null
      historySyncDone = false
      if (shouldReconnect) setTimeout(startWhatsApp, 5000)
    }
  })

  // ── HISTORIQUE COMPLET ──────────────────────────────────
  // Cet event se declenche automatiquement lors de la sync initiale
  // Il peut etre emis plusieurs fois (batches) — isLatest=true sur le dernier
  sock.ev.on('messaging-history.set', async ({ chats: waChats, messages: waMsgs, isLatest }) => {
    // 1. Sauvegarder les chats
    for (const chat of (waChats || [])) {
      const existing = chatList.get(chat.id) || {}
      await saveChat(chat.id, {
        name: chat.name || chat.subject || existing.name || chat.id.split('@')[0],
        lastMessage: existing.lastMessage || '',
        timestamp: Number(chat.conversationTimestamp) || existing.timestamp || 0,
        unreadCount: chat.unreadCount || existing.unreadCount || 0,
      })
    }

    // 2. Ingerer les messages
    const before = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)
    const added = await ingestBatch(waMsgs)
    const after = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)

    console.log(`📚 Lot historique: +${added} msgs sauvegardes (${chatList.size} chats, ${after} en memoire)`)

    if (isLatest) {
      historySyncDone = true
      const total = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)
      console.log(`🎉 Historique complet sync : ${chatList.size} chats, ${total} messages !`)
    }
  })

  // Fallback chats.set (anciennes versions)
  sock.ev.on('chats.set', async ({ chats: waChats }) => {
    for (const chat of (waChats || [])) {
      if (!chatList.has(chat.id)) {
        await saveChat(chat.id, {
          name: chat.name || chat.subject || chat.id.split('@')[0],
          lastMessage: '',
          timestamp: Number(chat.conversationTimestamp) || 0,
          unreadCount: chat.unreadCount || 0,
        })
      }
    }
    console.log(`📋 chats.set: ${waChats?.length || 0} chats enregistres`)
  })

  // ── Nouveaux messages en temps reel ──────────────────────
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    for (const msg of messages) {
      if (!msg.message) continue
      const chatId = msg.key.remoteJid
      const formatted = formatMessage(msg)

      await saveMessage(chatId, formatted, msg.pushName || '')

      // Mettre a jour ou creer chatList
      const existing = chatList.get(chatId) || {}
      await saveChat(chatId, {
        name: msg.pushName || existing.name || chatId.split('@')[0],
        lastMessage: formatted.body,
        timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
        unreadCount: msg.key.fromMe ? 0 : (existing.unreadCount || 0) + 1,
      })

      if (!msg.key.fromMe && formatted.body) {
        console.log(`📨 ${msg.pushName || chatId.split('@')[0]}: ${formatted.body.slice(0, 60)}`)

        // Envoyer vers le backend pour analyse (optionnel)
        if (TWIN_API) {
          fetch(`${TWIN_API}/whatsapp-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              chatId,
              message: formatted.body,
              pushName: msg.pushName,
              fromMe: false,
            }),
          }).catch(() => {})
        }
      }
    }
  })
}

// ─────────────────────────────────────────────────────────
// Demarrage automatique
// ─────────────────────────────────────────────────────────
app.listen(PORT, async () => {
  console.log(`\n🤖 Digital Twin — WhatsApp Bridge (Cloud)`)
  console.log(`🌐 API REST  : http://localhost:${PORT}`)
  console.log(`🔗 Backend   : ${TWIN_API}`)
  console.log(`💾 Supabase  : ${supabase ? 'connecte' : 'non configure'}`)
  console.log(`📁 Auth dir  : ${AUTH_DIR}\n`)

  // Demarrer la connexion WhatsApp automatiquement
  await startWhatsApp()
})
