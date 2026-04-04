import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

// Le bridge WhatsApp tourne sur le port 3001 (local ou Render)
const WA_BRIDGE = import.meta.env.VITE_WA_BRIDGE_URL || 'http://localhost:3001'

export default function WhatsAppPanel({ api }) {
  const [status, setStatus] = useState('disconnected')  // disconnected | qr | connected
  const [qr, setQr] = useState(null)
  const [chats, setChats] = useState([])
  const [selectedChat, setSelectedChat] = useState(null)
  const [messages, setMessages] = useState([])
  const [suggestion, setSuggestion] = useState(null)
  const [loading, setLoading] = useState(false)
  const pollRef = useRef(null)

  useEffect(() => {
    checkStatus()
    pollRef.current = setInterval(checkStatus, 3000)
    return () => clearInterval(pollRef.current)
  }, [])

  useEffect(() => {
    if (status === 'connected') loadChats()
  }, [status])

  async function checkStatus() {
    try {
      const res = await axios.get(`${WA_BRIDGE}/status`)
      setStatus(res.data.status)
      if (res.data.qr) setQr(res.data.qr)
      if (res.data.status === 'connected') setQr(null)
    } catch {
      setStatus('bridge_offline')
    }
  }

  async function startConnection() {
    try {
      await axios.post(`${WA_BRIDGE}/connect`)
      setStatus('qr')
    } catch {
      alert('Bridge WhatsApp hors ligne. Lance : node whatsapp-bridge/index.js')
    }
  }

  async function loadChats() {
    try {
      const res = await axios.get(`${WA_BRIDGE}/chats`)
      setChats(res.data.chats || [])
    } catch {}
  }

  async function selectChat(chat) {
    setSelectedChat(chat)
    setLoading(true)
    setSuggestion(null)
    try {
      const res = await axios.get(`${WA_BRIDGE}/messages/${chat.id}`)
      setMessages(res.data.messages || [])
      // Auto-suggest sur le dernier message reçu
      const lastIncoming = res.data.messages?.filter(m => !m.fromMe).slice(-1)[0]
      if (lastIncoming) await getSuggestion(lastIncoming.body)
    } catch {}
    setLoading(false)
  }

  async function getSuggestion(msgText) {
    try {
      const res = await axios.post(`${api}/suggest`, {
        message: msgText,
        person_type: 'close_friend',
      })
      setSuggestion(res.data)
    } catch {}
  }

  async function sendResponse(text) {
    if (!selectedChat) return
    try {
      await axios.post(`${WA_BRIDGE}/send`, {
        chatId: selectedChat.id,
        message: text,
      })
      setSuggestion(null)
      await selectChat(selectedChat)
    } catch {
      alert('Erreur envoi message')
    }
  }

  // ── Rendu selon l'état ────────────────────────────────────
  if (status === 'bridge_offline') return (
    <div>
      <h2 style={s.title}>📱 WhatsApp — Connexion QR</h2>
      <div style={s.card}>
        <div style={s.bigIcon}>🔌</div>
        <h3 style={{ color: '#f87171', marginBottom: 8 }}>Bridge hors ligne</h3>
        <p style={s.muted}>Le bridge WhatsApp ne tourne pas encore.</p>
        <p style={s.muted}>Dans un nouveau terminal, lance :</p>
        <div style={s.codeBlock}>
          cd whatsapp-bridge{'\n'}
          npm install{'\n'}
          node index.js
        </div>
        <button style={s.btn} onClick={checkStatus}>🔄 Vérifier à nouveau</button>
      </div>
    </div>
  )

  if (status === 'disconnected') return (
    <div>
      <h2 style={s.title}>📱 WhatsApp — Connexion QR</h2>
      <div style={s.card}>
        <div style={s.bigIcon}>📱</div>
        <h3 style={{ color: '#e2e8f0', marginBottom: 8 }}>Connecter ton WhatsApp</h3>
        <p style={s.muted}>Le twin va lire tes messages et suggérer des réponses dans ton style.</p>
        <p style={s.muted}>Ton entourage ne saura pas que c'est le twin qui répond (sauf si tu leur dis).</p>
        <button style={s.btnGreen} onClick={startConnection}>
          📲 Scanner le QR code WhatsApp
        </button>
      </div>
    </div>
  )

  if (status === 'qr' && qr) return (
    <div>
      <h2 style={s.title}>📱 Scanner le QR code</h2>
      <div style={{ ...s.card, textAlign: 'center' }}>
        <p style={{ ...s.muted, marginBottom: 16 }}>
          Ouvre WhatsApp → Appareils connectés → Connecter un appareil
        </p>
        <img
          src={qr}
          alt="QR Code WhatsApp"
          style={{ width: 250, height: 250, borderRadius: 12, background: '#fff', padding: 8 }}
        />
        <p style={{ ...s.muted, marginTop: 16 }}>En attente du scan...</p>
        <div style={s.qrDot} />
      </div>
    </div>
  )

  if (status === 'connected') return (
    <div>
      <h2 style={s.title}>📱 WhatsApp connecté ✅</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
        {/* Liste des chats */}
        <div style={s.card}>
          <div style={{ fontSize: 12, color: '#64748b', textTransform: 'uppercase', marginBottom: 12 }}>
            Conversations récentes
          </div>
          {chats.length === 0 ? (
            <p style={s.muted}>Chargement...</p>
          ) : chats.map(chat => (
            <div
              key={chat.id}
              onClick={() => selectChat(chat)}
              style={{
                ...s.chatItem,
                background: selectedChat?.id === chat.id ? '#1e3a5f' : 'transparent',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 14 }}>{chat.name}</div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                {chat.lastMessage?.slice(0, 40)}...
              </div>
            </div>
          ))}
        </div>

        {/* Messages + suggestion */}
        <div>
          {!selectedChat ? (
            <div style={{ ...s.card, textAlign: 'center', padding: 40 }}>
              <p style={s.muted}>← Sélectionne une conversation</p>
            </div>
          ) : (
            <>
              <div style={{ ...s.card, maxHeight: 300, overflowY: 'auto' }}>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 12 }}>
                  {selectedChat.name}
                </div>
                {loading ? <p style={s.muted}>Chargement...</p> : messages.slice(-15).map((m, i) => (
                  <div key={i} style={{
                    ...s.msg,
                    alignSelf: m.fromMe ? 'flex-end' : 'flex-start',
                    background: m.fromMe ? '#1e3a5f' : '#1e293b',
                  }}>
                    {m.body}
                  </div>
                ))}
              </div>

              {suggestion && (
                <div style={s.card}>
                  <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
                    🤖 Réponse suggérée ({Math.round(suggestion.confidence * 100)}%)
                  </div>
                  <div style={s.suggestionBox}>{suggestion.response}</div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button style={s.btnGreen} onClick={() => sendResponse(suggestion.response)}>
                      ✅ Envoyer
                    </button>
                    {suggestion.alternatives?.[0] && (
                      <button style={s.btn} onClick={() => sendResponse(suggestion.alternatives[0])}>
                        🔄 Alternative
                      </button>
                    )}
                    <button style={{ ...s.btn, color: '#f87171' }}
                      onClick={() => setSuggestion(null)}>
                      ✕ Ignorer
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )

  return <div style={s.muted}>Connexion en cours...</div>
}

const s = {
  title: { fontSize: 20, fontWeight: 700, color: '#f1f5f9', marginBottom: 20 },
  card: {
    background: '#1e293b', borderRadius: 12, padding: 24,
    border: '1px solid #334155', marginBottom: 16,
  },
  muted: { color: '#64748b', fontSize: 14, lineHeight: 1.6 },
  bigIcon: { fontSize: 48, marginBottom: 12 },
  codeBlock: {
    background: '#0f172a', borderRadius: 8, padding: '12px 16px',
    fontFamily: 'monospace', fontSize: 13, color: '#86efac',
    margin: '12px 0', whiteSpace: 'pre',
  },
  btn: {
    background: '#0f172a', color: '#94a3b8', border: '1px solid #334155',
    borderRadius: 8, padding: '10px 18px', fontSize: 14, cursor: 'pointer', marginTop: 12,
  },
  btnGreen: {
    background: '#166534', color: '#86efac', border: 'none',
    borderRadius: 8, padding: '11px 22px', fontSize: 14, fontWeight: 600, cursor: 'pointer',
  },
  chatItem: {
    padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
    marginBottom: 4, transition: 'background 0.1s',
  },
  msg: {
    maxWidth: '75%', padding: '8px 12px', borderRadius: 8,
    fontSize: 14, marginBottom: 6, display: 'flex',
  },
  suggestionBox: {
    background: '#0f172a', borderLeft: '3px solid #22c55e',
    borderRadius: '0 8px 8px 0', padding: '14px', color: '#e2e8f0', fontSize: 15,
  },
  qrDot: {
    width: 10, height: 10, borderRadius: '50%', background: '#22c55e',
    margin: '12px auto 0', animation: 'pulse 1.5s infinite',
  },
}
