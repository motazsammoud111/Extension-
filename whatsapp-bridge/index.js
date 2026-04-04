/**
 * whatsapp-bridge/index.js
 * Bridge WhatsApp ↔ Digital Twin AI via Baileys (QR code, pas de numéro pro requis)
 *
 * Ce bridge tourne LOCALEMENT sur ta machine (port 3001).
 * Il expose une API REST que le frontend React consomme.
 *
 * Lancement :
 *   npm install
 *   node index.js
 */

import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import QRCode from 'qrcode'
import pino from 'pino'
import { createRequire } from 'module'
import { existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

// ── Baileys (import dynamique pour compatibilité ESM) ──────────────────
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = await import('@whiskeysockets/baileys')

// ─────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────

const PORT       = process.env.WA_BRIDGE_PORT || 3001
const AUTH_DIR   = join(__dirname, '.wa_auth')
const TWIN_API   = process.env.TWIN_API_URL || 'http://localhost:8000'
const AUTO_REPLY = process.env.WA_AUTO_REPLY === 'true'

if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true })

// ─────────────────────────────────────────────────────────────────────
// État global
// ─────────────────────────────────────────────────────────────────────

let sock = null
let qrDataUrl = null
let connectionStatus = 'disconnected'   // disconnected | qr | connected
const messageCache = new Map()          // chatId → [messages]
const MAX_CACHE = 30                    // messages max par chat

// ─────────────────────────────────────────────────────────────────────
// Express API
// ─────────────────────────────────────────────────────────────────────

const app = express()
app.use(cors({ origin: '*' }))
app.use(express.json())

// Statut
app.get('/status', (req, res) => {
  res.json({
    status: connectionStatus,
    qr: qrDataUrl,
    connected: connectionStatus === 'connected',
  })
})

// Connecter WhatsApp (génère QR)
app.post('/connect', async (req, res) => {
  if (connectionStatus === 'connected') {
    return res.json({ message: 'Déjà connecté' })
  }
  await startWhatsApp()
  res.json({ message: 'Connexion initiée — scanne le QR code' })
})

// Déconnecter
app.post('/disconnect', async (req, res) => {
  if (sock) {
    await sock.logout()
    sock = null
    connectionStatus = 'disconnected'
    qrDataUrl = null
  }
  res.json({ message: 'Déconnecté' })
})

// Liste des chats récents
app.get('/chats', async (req, res) => {
  if (!sock || connectionStatus !== 'connected') {
    return res.status(503).json({ error: 'Non connecté' })
  }
  try {
    // Récupérer les chats depuis le store Baileys
    const chats = []
    for (const [id, msgs] of messageCache.entries()) {
      if (msgs.length === 0) continue
      const last = msgs[msgs.length - 1]
      chats.push({
        id,
        name: last.pushName || id.split('@')[0],
        lastMessage: last.message?.conversation || last.message?.extendedTextMessage?.text || '[media]',
        timestamp: last.messageTimestamp,
        unreadCount: msgs.filter(m => !m.key?.fromMe).length,
      })
    }
    chats.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
    res.json({ chats: chats.slice(0, 20) })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// Messages d'un chat
app.get('/messages/:chatId', (req, res) => {
  const msgs = messageCache.get(req.params.chatId) || []
  const formatted = msgs.map(m => ({
    id: m.key?.id,
    fromMe: m.key?.fromMe,
    body: m.message?.conversation
       || m.message?.extendedTextMessage?.text
       || '[media]',
    timestamp: m.messageTimestamp,
    pushName: m.pushName,
  }))
  res.json({ messages: formatted })
})

// Envoyer un message
app.post('/send', async (req, res) => {
  const { chatId, message } = req.body
  if (!sock || connectionStatus !== 'connected') {
    return res.status(503).json({ error: 'Non connecté à WhatsApp' })
  }
  if (!chatId || !message) {
    return res.status(400).json({ error: 'chatId et message requis' })
  }
  try {
    await sock.sendMessage(chatId, { text: message })
    console.log(`✅ Message envoyé à ${chatId}`)
    res.json({ success: true })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// Suggestion manuelle pour un message
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

// ─────────────────────────────────────────────────────────────────────
// Baileys — Connexion WhatsApp
// ─────────────────────────────────────────────────────────────────────

async function startWhatsApp() {
  if (sock) return

  const logger = pino({ level: 'silent' })   // silencieux pour ne pas polluer les logs
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version } = await fetchLatestBaileysVersion()

  console.log(`\n🟢 Baileys v${version.join('.')} — Connexion WhatsApp...`)

  sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    printQRInTerminal: true,  // affiche aussi dans le terminal
    logger,
    generateHighQualityLinkPreview: false,
    syncFullHistory: false,
  })

  // ── Événements ─────────────────────────────────────────────────────

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      connectionStatus = 'qr'
      qrDataUrl = await QRCode.toDataURL(qr)
      console.log('📱 QR code généré — ouvre le frontend pour scanner')
    }

    if (connection === 'open') {
      connectionStatus = 'connected'
      qrDataUrl = null
      console.log('✅ WhatsApp connecté !')
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      const shouldReconnect = code !== DisconnectReason.loggedOut

      console.log(`❌ Déconnecté (code ${code}) — ${shouldReconnect ? 'reconnexion...' : 'logged out'}`)

      sock = null
      connectionStatus = 'disconnected'
      qrDataUrl = null

      if (shouldReconnect) {
        setTimeout(startWhatsApp, 3000)
      }
    }
  })

  // Réception de messages
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return

    for (const msg of messages) {
      if (!msg.message) continue

      const chatId = msg.key.remoteJid
      const isGroup = chatId.endsWith('@g.us')
      const fromMe = msg.key.fromMe
      const text = msg.message?.conversation
                || msg.message?.extendedTextMessage?.text
                || null

      // Cacher les messages dans le cache
      if (!messageCache.has(chatId)) messageCache.set(chatId, [])
      const chatMsgs = messageCache.get(chatId)
      chatMsgs.push(msg)
      if (chatMsgs.length > MAX_CACHE) chatMsgs.shift()

      // Log
      if (!fromMe && text) {
        const sender = msg.pushName || chatId.split('@')[0]
        console.log(`📨 ${sender}: ${text.slice(0, 60)}`)
      }

      // Auto-reply si activé (mode automatique — utilise avec prudence)
      if (AUTO_REPLY && !fromMe && !isGroup && text) {
        try {
          const res = await fetch(`${TWIN_API}/suggest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, person_type: 'close_friend' }),
          })
          const data = await res.json()
          if (data.response) {
            // Délai naturel (entre 2 et 8 secondes) pour paraître humain
            const delay = 2000 + Math.random() * 6000
            setTimeout(async () => {
              await sock.sendMessage(chatId, { text: data.response })
              console.log(`🤖 Auto-reply envoyé à ${chatId}`)
            }, delay)
          }
        } catch (e) {
          console.error('Erreur auto-reply:', e.message)
        }
      }
    }
  })
}

// ─────────────────────────────────────────────────────────────────────
// Démarrage
// ─────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`\n🤖 Digital Twin — WhatsApp Bridge`)
  console.log(`🌐 API REST : http://localhost:${PORT}`)
  console.log(`🔗 Backend  : ${TWIN_API}`)
  console.log(`🔄 Auto-reply : ${AUTO_REPLY ? '⚠️  ACTIVÉ' : 'désactivé (mode suggestion)'}`)
  console.log(`\n→ Ouvre le frontend et clique sur "📱 WhatsApp" pour scanner le QR\n`)
})
