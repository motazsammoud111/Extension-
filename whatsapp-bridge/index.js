/**
 * whatsapp-bridge/index.js — version corrigée
 * - Extraction complète via messaging-history.set (Baileys v2)
 * - Support médias avec placeholders
 * - Endpoint /load-more pour pagination
 */

import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import QRCode from 'qrcode'
import pino from 'pino'
import { existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

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
const PORT     = process.env.WA_BRIDGE_PORT || 3001
const AUTH_DIR = join(__dirname, '.wa_auth')
const TWIN_API = process.env.TWIN_API_URL || 'http://localhost:8000'
const AUTO_REPLY = process.env.WA_AUTO_REPLY === 'true'

if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })

// ─────────────────────────────────────────────────────────
// Etat global
// ─────────────────────────────────────────────────────────
let sock             = null
let qrDataUrl        = null
let connectionStatus = 'disconnected'
let historySyncDone  = false

// chatId -> [{ id, fromMe, body, timestamp, pushName, mediaType, caption }]
const messageCache = new Map()
// chatId -> { name, lastMessage, timestamp, unreadCount }
const chatList     = new Map()

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
app.get('/status', (req, res) => {
  const total = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)
  res.json({
    status: connectionStatus,
    qr: qrDataUrl,
    connected: connectionStatus === 'connected',
    chats: chatList.size,
    messages: total,
    historySyncDone,
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

// Liste des chats triés par date
app.get('/chats', (req, res) => {
  const result = Array.from(chatList.entries()).map(([id, meta]) => ({ id, ...meta }))
  result.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
  res.json({
    chats: result.slice(0, 100),
    total: chatList.size,
    syncDone: historySyncDone,
  })
})

// Messages d'un chat
app.get('/messages/:chatId', (req, res) => {
  const msgs = messageCache.get(req.params.chatId) || []
  // Trier par timestamp croissant
  const sorted = [...msgs].sort((a, b) => (Number(a.timestamp) || 0) - (Number(b.timestamp) || 0))
  res.json({ messages: sorted })
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
    if (!messageCache.has(chatId)) messageCache.set(chatId, [])
    messageCache.get(chatId).push(newMsg)
    res.json({ success: true })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// Suggestion de reponse via le backend IA
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

// Charger plus de messages (pagination via Baileys)
app.get('/load-more/:chatId/:cursor?', async (req, res) => {
  if (!sock || connectionStatus !== 'connected')
    return res.status(503).json({ error: 'Non connecte' })
  const { chatId, cursor } = req.params
  try {
    const msgs = await sock.loadMessages(chatId, 30, cursor ? { before: { id: cursor, fromMe: false } } : undefined)
    const formatted = (msgs || []).map(m => formatMessage(m))
    res.json({ messages: formatted, nextCursor: msgs?.[msgs.length - 1]?.key?.id })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// ─────────────────────────────────────────────────────────
// Utilitaires
// ─────────────────────────────────────────────────────────
function formatMessage(msg) {
  let body = '', mediaType = null, caption = ''

  if (msg.message?.conversation) {
    body = msg.message.conversation
  } else if (msg.message?.extendedTextMessage?.text) {
    body = msg.message.extendedTextMessage.text
  } else if (msg.message?.imageMessage) {
    mediaType = 'image'
    caption = msg.message.imageMessage.caption || ''
    body = caption ? `📷 ${caption}` : '📷 Image'
  } else if (msg.message?.videoMessage) {
    mediaType = 'video'
    caption = msg.message.videoMessage.caption || ''
    body = caption ? `🎥 ${caption}` : '🎥 Video'
  } else if (msg.message?.documentMessage) {
    mediaType = 'document'
    body = `📄 ${msg.message.documentMessage.fileName || 'Document'}`
  } else if (msg.message?.audioMessage) {
    mediaType = 'audio'
    body = '🎵 Message vocal'
  } else if (msg.message?.stickerMessage) {
    mediaType = 'sticker'
    body = '🖼️ Sticker'
  } else if (msg.message?.reactionMessage) {
    body = `${msg.message.reactionMessage.text || '👍'} (reaction)`
  } else if (msg.message?.contactMessage) {
    body = `👤 Contact: ${msg.message.contactMessage.displayName || ''}`
  } else if (msg.message?.locationMessage) {
    body = '📍 Localisation'
  } else {
    body = '[Media]'
  }

  return {
    id: msg.key?.id || String(Date.now()),
    fromMe: !!msg.key?.fromMe,
    body,
    timestamp: msg.messageTimestamp,
    pushName: msg.pushName || '',
    mediaType,
    caption,
  }
}

/**
 * Ingere un tableau de WAMessage dans messageCache + met a jour chatList
 */
function ingestMessages(waMsgs) {
  if (!waMsgs?.length) return
  for (const msg of waMsgs) {
    if (!msg?.message) continue
    const chatId = msg.key?.remoteJid
    if (!chatId) continue
    const formatted = formatMessage(msg)
    if (!messageCache.has(chatId)) messageCache.set(chatId, [])
    const arr = messageCache.get(chatId)
    // Eviter les doublons
    if (!arr.find(m => m.id === formatted.id)) {
      arr.push(formatted)
    }
    // Mettre a jour lastMessage
    if (chatList.has(chatId)) {
      const chat = chatList.get(chatId)
      const ts = Number(msg.messageTimestamp) || 0
      if (ts > (chat.timestamp || 0)) {
        chat.lastMessage = formatted.body
        chat.timestamp = ts
      }
    }
  }
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
    syncFullHistory: true,      // demander tout l'historique a WhatsApp
    markOnlineOnConnect: false,
    getMessage: async (key) => {
      // Callback pour retrouver un message depuis le cache
      const msgs = messageCache.get(key.remoteJid) || []
      const found = msgs.find(m => m.id === key.id)
      return found ? { conversation: found.body } : undefined
    },
  })

  sock.ev.on('creds.update', saveCreds)

  // ── QR / connexion ──────────────────────────────────────
  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      connectionStatus = 'qr'
      qrDataUrl = await QRCode.toDataURL(qr)
      console.log('📱 QR code genere')
    }

    if (connection === 'open') {
      connectionStatus = 'connected'
      qrDataUrl = null
      historySyncDone = false
      console.log('✅ WhatsApp connecte ! En attente de la sync historique...')
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      const shouldReconnect = code !== DisconnectReason.loggedOut
      console.log(`❌ Deconnecte (code ${code}) — ${shouldReconnect ? 'reconnexion...' : 'logged out'}`)
      sock = null
      connectionStatus = 'disconnected'
      qrDataUrl = null
      historySyncDone = false
      if (shouldReconnect) setTimeout(startWhatsApp, 3000)
    }
  })

  // ── HISTORIQUE COMPLET (evenement Baileys v2) ────────────
  // Cet evenement se declenche automatiquement pendant la sync initiale
  // Il peut etre emis plusieurs fois (par lots) — isLatest=true sur le dernier lot
  sock.ev.on('messaging-history.set', ({ chats: waChats, messages: waMsgs, isLatest }) => {
    // 1. Mettre a jour la liste des chats
    for (const chat of (waChats || [])) {
      const existing = chatList.get(chat.id)
      chatList.set(chat.id, {
        name: chat.name || chat.subject || existing?.name || chat.id.split('@')[0],
        lastMessage: existing?.lastMessage || '',
        timestamp: Number(chat.conversationTimestamp) || existing?.timestamp || 0,
        unreadCount: chat.unreadCount || existing?.unreadCount || 0,
      })
    }

    // 2. Ingerer les messages de ce lot
    const before = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)
    ingestMessages(waMsgs)
    const after = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)

    console.log(`📚 Lot historique recu : +${after - before} msgs (total: ${chatList.size} chats, ${after} msgs)`)

    if (isLatest) {
      historySyncDone = true
      const total = Array.from(messageCache.values()).reduce((s, a) => s + a.length, 0)
      console.log(`🎉 Historique complet synchronise : ${chatList.size} chats, ${total} messages !`)
    }
  })

  // Fallback pour anciennes versions de Baileys
  sock.ev.on('chats.set', ({ chats: waChats }) => {
    for (const chat of (waChats || [])) {
      if (!chatList.has(chat.id)) {
        chatList.set(chat.id, {
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
      if (!messageCache.has(chatId)) messageCache.set(chatId, [])
      const arr = messageCache.get(chatId)
      if (!arr.find(m => m.id === formatted.id)) arr.push(formatted)

      // Mettre a jour ou creer chatList
      if (!chatList.has(chatId)) {
        chatList.set(chatId, {
          name: msg.pushName || chatId.split('@')[0],
          lastMessage: formatted.body,
          timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
          unreadCount: msg.key.fromMe ? 0 : 1,
        })
      } else {
        const chat = chatList.get(chatId)
        chat.lastMessage = formatted.body
        chat.timestamp = Number(msg.messageTimestamp) || chat.timestamp
        if (!msg.key.fromMe) chat.unreadCount = (chat.unreadCount || 0) + 1
      }

      if (!msg.key.fromMe && formatted.body) {
        console.log(`📨 ${msg.pushName || chatId.split('@')[0]}: ${formatted.body.slice(0, 60)}`)
      }
    }
  })
}

// ─────────────────────────────────────────────────────────
// Demarrage
// ─────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🤖 Digital Twin — WhatsApp Bridge`)
  console.log(`🌐 API REST : http://localhost:${PORT}`)
  console.log(`🔗 Backend  : ${TWIN_API}`)
  console.log(`🔄 Auto-reply : ${AUTO_REPLY ? 'ACTIVE' : 'desactive'}`)
  console.log(`→ Ouvre le frontend et scanne le QR\n`)
})

startWhatsApp()
