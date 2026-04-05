/**
 * whatsapp-bridge/index.js — version professionnelle
 * - Chargement complet de l’historique (tous chats + messages)
 * - Support des médias (images, vidéos, documents) avec placeholders
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
const PORT = process.env.WA_BRIDGE_PORT || 3001
const AUTH_DIR = join(__dirname, '.wa_auth')
const TWIN_API = process.env.TWIN_API_URL || 'http://localhost:8000'
const AUTO_REPLY = process.env.WA_AUTO_REPLY === 'true'

if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })

// ─────────────────────────────────────────────────────────
// État global
// ─────────────────────────────────────────────────────────
let sock = null
let qrDataUrl = null
let connectionStatus = 'disconnected'
const messageCache = new Map()      // chatId → [{ id, fromMe, body, timestamp, mediaType?, caption? }]
const chatList = new Map()          // chatId → { name, lastMessage, timestamp, unreadCount }

const app = express()

// CORS pour localhost + Vercel
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
  res.json({ status: connectionStatus, qr: qrDataUrl, connected: connectionStatus === 'connected' })
})

app.post('/connect', async (req, res) => {
  if (connectionStatus === 'connected') return res.json({ message: 'Déjà connecté' })
  await startWhatsApp()
  res.json({ message: 'Connexion initiée' })
})

app.post('/disconnect', async (req, res) => {
  if (sock) await sock.logout()
  sock = null
  connectionStatus = 'disconnected'
  qrDataUrl = null
  res.json({ message: 'Déconnecté' })
})

app.get('/chats', (req, res) => {
  const result = Array.from(chatList.entries()).map(([id, meta]) => ({ id, ...meta }))
  result.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
  res.json({ chats: result.slice(0, 30) })
})

app.get('/messages/:chatId', (req, res) => {
  const msgs = messageCache.get(req.params.chatId) || []
  res.json({ messages: msgs })
})

app.post('/send', async (req, res) => {
  const { chatId, message } = req.body
  if (!sock || connectionStatus !== 'connected') return res.status(503).json({ error: 'Non connecté' })
  try {
    await sock.sendMessage(chatId, { text: message })
    // Ajouter le message envoyé au cache (optimiste)
    const newMsg = { id: Date.now().toString(), fromMe: true, body: message, timestamp: Date.now() / 1000 }
    if (!messageCache.has(chatId)) messageCache.set(chatId, [])
    messageCache.get(chatId).push(newMsg)
    res.json({ success: true })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

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

// Endpoint pour charger plus de messages (pagination)
app.get('/load-more/:chatId/:cursor?', async (req, res) => {
  if (!sock || connectionStatus !== 'connected') return res.status(503).json({ error: 'Non connecté' })
  const { chatId, cursor } = req.params
  try {
    // Charge 30 messages avant le curseur (si fourni)
    const msgs = await sock.loadMessages(chatId, 30, cursor)
    const formatted = msgs.map(m => formatMessage(m))
    res.json({ messages: formatted, nextCursor: msgs[msgs.length-1]?.key?.id })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// ─────────────────────────────────────────────────────────
// Fonctions utilitaires
// ─────────────────────────────────────────────────────────
function formatMessage(msg) {
  let body = ''
  let mediaType = null
  let caption = ''

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
    body = caption ? `🎥 ${caption}` : '🎥 Vidéo'
  } else if (msg.message?.documentMessage) {
    mediaType = 'document'
    body = `📄 ${msg.message.documentMessage.fileName || 'Document'}`
  } else if (msg.message?.audioMessage) {
    mediaType = 'audio'
    body = '🎵 Message vocal'
  } else if (msg.message?.stickerMessage) {
    mediaType = 'sticker'
    body = '🖼️ Sticker'
  } else {
    body = '[Média non supporté]'
  }

  return {
    id: msg.key.id,
    fromMe: msg.key.fromMe,
    body,
    timestamp: msg.messageTimestamp,
    pushName: msg.pushName,
    mediaType,
    caption,
  }
}

// ─────────────────────────────────────────────────────────
// Chargement de l’historique complet
// ─────────────────────────────────────────────────────────
async function loadFullHistory() {
  if (!sock) return
  console.log('🔄 Chargement de tout l’historique des chats et messages...')

  try {
    // Récupérer la liste de tous les chats
    let allChats = []
    if (typeof sock.chats?.all === 'function') {
      allChats = await sock.chats.all()
    } else if (typeof sock.groupFetchAllParticipating === 'function') {
      const groups = await sock.groupFetchAllParticipating()
      allChats = Object.values(groups)
    }

    if (!allChats.length) {
      console.log('⚠️ Aucun chat trouvé. Envoie/reçois des messages pour en créer.')
      return
    }

    console.log(`📋 ${allChats.length} chats trouvés. Chargement des messages...`)

    for (const chat of allChats) {
      const chatId = chat.id
      // Mettre à jour chatList
      chatList.set(chatId, {
        name: chat.name || chat.subject || chatId.split('@')[0],
        lastMessage: '',
        timestamp: chat.conversationTimestamp || 0,
        unreadCount: chat.unreadCount || 0,
      })

      // Charger les 50 derniers messages
      if (typeof sock.loadMessages === 'function') {
        try {
          const msgs = await sock.loadMessages(chatId, 50)
          if (msgs && msgs.length) {
            const formatted = msgs.map(formatMessage)
            messageCache.set(chatId, formatted.reverse()) // ordre chronologique
            console.log(`   ✅ ${chatId} : ${msgs.length} messages chargés`)
          } else {
            console.log(`   ⚠️ ${chatId} : aucun message trouvé`)
          }
        } catch (err) {
          console.error(`   ❌ Erreur pour ${chatId}:`, err.message)
        }
      }
    }

    const totalMessages = Array.from(messageCache.values()).reduce((sum, arr) => sum + arr.length, 0)
    console.log(`🎉 Chargement terminé : ${chatList.size} chats, ${totalMessages} messages au total.`)
  } catch (err) {
    console.error('Erreur dans loadFullHistory:', err)
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
    printQRInTerminal: false,      // on gère via frontend
    logger,
    syncFullHistory: true,          // important
    markOnlineOnConnect: false,
  })

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      connectionStatus = 'qr'
      qrDataUrl = await QRCode.toDataURL(qr)
      console.log('📱 QR code généré')
    }

    if (connection === 'open') {
      connectionStatus = 'connected'
      qrDataUrl = null
      console.log('✅ WhatsApp connecté !')
      await loadFullHistory()
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      const shouldReconnect = code !== DisconnectReason.loggedOut
      console.log(`❌ Déconnecté (code ${code}) — ${shouldReconnect ? 'reconnexion...' : 'logged out'}`)
      sock = null
      connectionStatus = 'disconnected'
      qrDataUrl = null
      if (shouldReconnect) setTimeout(startWhatsApp, 3000)
    }
  })

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    for (const msg of messages) {
      if (!msg.message) continue
      const chatId = msg.key.remoteJid
      const formatted = formatMessage(msg)
      if (!messageCache.has(chatId)) messageCache.set(chatId, [])
      const arr = messageCache.get(chatId)
      arr.push(formatted)
      if (arr.length > 200) arr.shift()  // garder max 200 messages
      // Mettre à jour chatList
      if (!chatList.has(chatId)) {
        chatList.set(chatId, { name: msg.pushName || chatId.split('@')[0], timestamp: Date.now() })
      }
      // Log
      if (!msg.key.fromMe && formatted.body) {
        console.log(`📨 ${msg.pushName || chatId}: ${formatted.body.slice(0, 60)}`)
      }
    }
  })
}

// ─────────────────────────────────────────────────────────
// Démarrage
// ─────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n🤖 Digital Twin — WhatsApp Bridge (historique complet + médias)`)
  console.log(`🌐 API REST : http://localhost:${PORT}`)
  console.log(`🔗 Backend  : ${TWIN_API}`)
  console.log(`🔄 Auto-reply : ${AUTO_REPLY ? 'ACTIVÉ' : 'désactivé'}\n`)
})