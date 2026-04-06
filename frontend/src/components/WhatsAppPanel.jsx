import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const WA_BRIDGE = import.meta.env.VITE_WA_BRIDGE_URL || 'http://localhost:3001'

// ── Formatage des timestamps ──────────────────────────────
function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(Number(ts) * 1000)
  const now = new Date()
  const diffDays = Math.floor((now - d) / 86400000)
  if (diffDays === 0) return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1) return 'Hier'
  if (diffDays < 7) return d.toLocaleDateString('fr-FR', { weekday: 'short' })
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })
}

function fmtFullTime(ts) {
  if (!ts) return ''
  const d = ts > 1e10 ? new Date(Number(ts)) : new Date(Number(ts) * 1000)
  return d.toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function WhatsAppPanel({ api }) {
  const [status, setStatus]               = useState('disconnected')
  const [qr, setQr]                       = useState(null)
  const [bridgeInfo, setBridgeInfo]       = useState({ chats: 0, messages: 0, syncDone: false })

  // Bridge chats
  const [bridgeChats, setBridgeChats]     = useState([])
  const [selectedChat, setSelectedChat]   = useState(null)
  const [bridgeMsgs, setBridgeMsgs]       = useState([])
  const [chatSearch, setChatSearch]       = useState('')

  // Suggestion IA
  const [suggestion, setSuggestion]       = useState(null)

  // Imported conversations
  const [importedConvs, setImportedConvs] = useState([])
  const [selectedImported, setSelectedImported] = useState(null)
  const [importedMsgs, setImportedMsgs]   = useState([])
  const [importSearch, setImportSearch]   = useState('')

  const [activeTab, setActiveTab]         = useState('bridge')
  const [loading, setLoading]             = useState(false)

  const messagesEndRef  = useRef(null)
  const pollingRef      = useRef(null)

  // ── Auto-scroll ────────────────────────────────────────
  const scrollToBottom = () =>
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })

  useEffect(() => { scrollToBottom() }, [bridgeMsgs, importedMsgs])

  // ── Polling statut ──────────────────────────────────────
  const checkStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${WA_BRIDGE}/status`)
      setStatus(res.data.status)
      if (res.data.qr) setQr(res.data.qr)
      else setQr(null)
      setBridgeInfo({
        chats: res.data.chats || 0,
        messages: res.data.messages || 0,
        syncDone: res.data.historySyncDone || false,
      })
    } catch {
      setStatus('bridge_offline')
    }
  }, [])

  useEffect(() => {
    checkStatus()
    pollingRef.current = setInterval(checkStatus, 3000)
    return () => clearInterval(pollingRef.current)
  }, [checkStatus])

  useEffect(() => {
    if (status === 'connected') loadBridgeChats()
  }, [status, bridgeInfo.chats])

  useEffect(() => {
    if (activeTab === 'imported') loadImportedConversations()
  }, [activeTab])

  useEffect(() => {
    if (selectedChat && activeTab === 'bridge') loadBridgeMsgs()
  }, [selectedChat])

  useEffect(() => {
    if (selectedImported && activeTab === 'imported') loadImportedMsgs()
  }, [selectedImported])

  // ── Bridge functions ────────────────────────────────────
  async function startConnection() {
    await axios.post(`${WA_BRIDGE}/connect`)
    setStatus('qr')
  }

  async function loadBridgeChats() {
    try {
      const res = await axios.get(`${WA_BRIDGE}/chats`)
      setBridgeChats(res.data.chats || [])
    } catch (err) { console.error(err) }
  }

  async function loadBridgeMsgs() {
    if (!selectedChat) return
    setLoading(true)
    try {
      const res = await axios.get(`${WA_BRIDGE}/messages/${encodeURIComponent(selectedChat.id)}`)
      setBridgeMsgs(res.data.messages || [])
      // Suggestion sur dernier message recu
      const lastIn = (res.data.messages || []).filter(m => !m.fromMe).slice(-1)[0]
      if (lastIn?.body) await getSuggestion(lastIn.body)
    } catch (err) { console.error(err) }
    setLoading(false)
  }

  async function getSuggestion(msgText) {
    if (!msgText || !api) return
    try {
      const res = await axios.post(`${api}/suggest`, {
        message: msgText, person_type: 'close_friend',
      })
      setSuggestion(res.data)
    } catch {}
  }

  async function sendResponse(text) {
    if (!selectedChat) return
    try {
      await axios.post(`${WA_BRIDGE}/send`, { chatId: selectedChat.id, message: text })
      setSuggestion(null)
      await loadBridgeMsgs()
    } catch { alert('Erreur envoi') }
  }

  // ── Imported functions ──────────────────────────────────
  async function loadImportedConversations() {
    try {
      const res = await axios.get(`${api}/conversations`)
      setImportedConvs(res.data.conversations || [])
    } catch (err) { console.error(err) }
  }

  async function loadImportedMsgs() {
    if (!selectedImported) return
    setLoading(true)
    try {
      const res = await axios.get(
        `${api}/conversations/${encodeURIComponent(selectedImported.name)}?limit=300`
      )
      setImportedMsgs(res.data.messages || [])
    } catch (err) { console.error(err) }
    setLoading(false)
  }

  // ── Filtres search ──────────────────────────────────────
  const filteredBridge = bridgeChats.filter(c =>
    c.name?.toLowerCase().includes(chatSearch.toLowerCase())
  )
  const filteredImported = importedConvs.filter(c =>
    c.name?.toLowerCase().includes(importSearch.toLowerCase())
  )

  // ── Rendu pages speciales ───────────────────────────────
  if (status === 'bridge_offline') return (
    <div style={S.card}>
      <div style={S.bigIcon}>🔌</div>
      <h3 style={{ color: '#f87171', marginBottom: 8 }}>Bridge hors ligne</h3>
      <p style={{ color: '#94a3b8', marginBottom: 16 }}>Lance dans WSL :</p>
      <code style={S.code}>cd ~/digital-twin-ai/whatsapp-bridge && npm start</code>
      <button style={{ ...S.btn, marginTop: 20 }} onClick={checkStatus}>🔄 Vérifier</button>
    </div>
  )

  if (status === 'disconnected') return (
    <div style={S.card}>
      <div style={S.bigIcon}>📱</div>
      <h3 style={{ marginBottom: 8 }}>Connecter WhatsApp</h3>
      <p style={{ color: '#94a3b8', marginBottom: 20 }}>
        Le twin lit tes messages et suggère des réponses en temps réel.
      </p>
      <button style={S.btnGreen} onClick={startConnection}>📲 Scanner le QR code</button>
    </div>
  )

  if (status === 'qr' && qr) return (
    <div style={{ ...S.card, textAlign: 'center' }}>
      <h3 style={{ marginBottom: 8 }}>📷 Scanner le QR code</h3>
      <p style={{ color: '#94a3b8', marginBottom: 16 }}>
        WhatsApp → Appareils connectés → Connecter un appareil
      </p>
      <img src={qr} alt="QR" style={{ width: 240, height: 240, background: '#fff', padding: 8, borderRadius: 12 }} />
      <div style={S.qrPulse} />
    </div>
  )

  // ── Vue principale ──────────────────────────────────────
  return (
    <div style={S.container}>
      {/* Header */}
      <div style={S.header}>
        <span style={S.headerTitle}>📱 WhatsApp connecté ✅</span>
        <span style={S.syncBadge}>
          {bridgeInfo.syncDone
            ? `✅ ${bridgeInfo.chats} chats · ${bridgeInfo.messages} msgs`
            : `⏳ Sync en cours... ${bridgeInfo.chats} chats`}
        </span>
        <button style={S.refreshBtn} onClick={loadBridgeChats} title="Actualiser">🔄</button>
      </div>

      {/* Tabs */}
      <div style={S.tabs}>
        <button
          onClick={() => setActiveTab('bridge')}
          style={{ ...S.tab, ...(activeTab === 'bridge' && S.tabActive) }}
        >
          💬 Messages en direct
          {bridgeChats.length > 0 && <span style={S.countBadge}>{bridgeChats.length}</span>}
        </button>
        <button
          onClick={() => setActiveTab('imported')}
          style={{ ...S.tab, ...(activeTab === 'imported' && S.tabActive) }}
        >
          📚 Historique importé
          {importedConvs.length > 0 && <span style={S.countBadge}>{importedConvs.length}</span>}
        </button>
      </div>

      {/* ── TAB BRIDGE ──────────────────────────────────── */}
      {activeTab === 'bridge' && (
        <div style={S.layout}>
          {/* Colonne gauche — liste des chats */}
          <div style={S.sidebar}>
            <input
              style={S.searchInput}
              placeholder="🔍 Rechercher..."
              value={chatSearch}
              onChange={e => setChatSearch(e.target.value)}
            />
            {filteredBridge.length === 0 && (
              <p style={S.muted}>
                {bridgeInfo.syncDone
                  ? 'Aucune conversation trouvée'
                  : '⏳ Sync en cours, patienter...'}
              </p>
            )}
            {filteredBridge.map(chat => (
              <div
                key={chat.id}
                onClick={() => { setSelectedChat(chat); setSuggestion(null) }}
                style={{
                  ...S.chatRow,
                  background: selectedChat?.id === chat.id ? '#1e3a5f' : 'transparent',
                  borderLeft: selectedChat?.id === chat.id ? '3px solid #60a5fa' : '3px solid transparent',
                }}
              >
                {/* Avatar */}
                <div style={S.avatar}>
                  {(chat.name || '?')[0].toUpperCase()}
                </div>
                <div style={S.chatInfo}>
                  <div style={S.chatMeta}>
                    <span style={S.chatName}>{chat.name}</span>
                    <span style={S.chatTime}>{fmtTime(chat.timestamp)}</span>
                  </div>
                  <div style={S.chatMeta}>
                    <span style={S.chatPreview}>
                      {chat.lastMessage ? chat.lastMessage.slice(0, 42) + (chat.lastMessage.length > 42 ? '...' : '') : '—'}
                    </span>
                    {chat.unreadCount > 0 && (
                      <span style={S.unreadBadge}>{chat.unreadCount}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Colonne droite — messages */}
          <div style={S.chatPane}>
            {!selectedChat ? (
              <div style={S.placeholder}>← Sélectionne une conversation</div>
            ) : (
              <>
                {/* Header chat */}
                <div style={S.chatHeader}>
                  <div style={{ ...S.avatar, width: 36, height: 36, fontSize: 16 }}>
                    {(selectedChat.name || '?')[0].toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15 }}>{selectedChat.name}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>
                      {selectedChat.id?.split('@')[0]}
                    </div>
                  </div>
                  <button style={{ ...S.refreshBtn, marginLeft: 'auto' }} onClick={loadBridgeMsgs}>🔄</button>
                </div>

                {/* Messages */}
                <div style={S.messagesArea}>
                  {loading && <p style={S.muted}>Chargement...</p>}
                  {bridgeMsgs.length === 0 && !loading && (
                    <p style={S.muted}>Aucun message disponible pour cette conversation.</p>
                  )}
                  {bridgeMsgs.map((msg, i) => (
                    <div key={msg.id || i} style={{ ...S.msgRow, justifyContent: msg.fromMe ? 'flex-end' : 'flex-start' }}>
                      {!msg.fromMe && (
                        <div style={{ ...S.avatarSmall }}>{(msg.pushName || selectedChat.name || '?')[0].toUpperCase()}</div>
                      )}
                      <div style={{ maxWidth: '70%' }}>
                        {!msg.fromMe && msg.pushName && (
                          <div style={S.senderName}>{msg.pushName}</div>
                        )}
                        <div style={{ ...S.bubble, ...(msg.fromMe ? S.bubbleMine : S.bubbleOther) }}>
                          {msg.body}
                        </div>
                        <div style={{ ...S.ts, textAlign: msg.fromMe ? 'right' : 'left' }}>
                          {fmtFullTime(msg.timestamp)}
                          {msg.fromMe && ' ✓'}
                        </div>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>

                {/* Suggestion IA */}
                {suggestion && (
                  <div style={S.suggBox}>
                    <div style={S.suggHeader}>
                      🤖 Réponse suggérée
                      <span style={S.confBadge}>{Math.round((suggestion.confidence || 0) * 100)}%</span>
                    </div>
                    <div style={S.suggText}>{suggestion.response}</div>
                    <div style={S.suggActions}>
                      <button style={S.btnGreen} onClick={() => sendResponse(suggestion.response)}>✅ Envoyer</button>
                      {suggestion.alternatives?.[0] && (
                        <button style={S.btnAlt} onClick={() => sendResponse(suggestion.alternatives[0])}>🔄 Alt.</button>
                      )}
                      <button style={S.btnIgnore} onClick={() => setSuggestion(null)}>✕</button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── TAB IMPORTED ─────────────────────────────────── */}
      {activeTab === 'imported' && (
        <div style={S.layout}>
          {/* Sidebar */}
          <div style={S.sidebar}>
            <input
              style={S.searchInput}
              placeholder="🔍 Rechercher..."
              value={importSearch}
              onChange={e => setImportSearch(e.target.value)}
            />
            {filteredImported.length === 0 && (
              <p style={S.muted}>Aucune conversation. Va dans <strong>Importer</strong>.</p>
            )}
            {filteredImported.map(conv => (
              <div
                key={conv.name}
                onClick={() => setSelectedImported(conv)}
                style={{
                  ...S.chatRow,
                  background: selectedImported?.name === conv.name ? '#1e3a5f' : 'transparent',
                  borderLeft: selectedImported?.name === conv.name ? '3px solid #60a5fa' : '3px solid transparent',
                }}
              >
                <div style={{ ...S.avatar, background: '#7c3aed' }}>
                  {(conv.name || '?')[0].toUpperCase()}
                </div>
                <div style={S.chatInfo}>
                  <div style={S.chatName}>{conv.name}</div>
                  <div style={{ ...S.chatPreview, marginTop: 2 }}>
                    {conv.message_count} messages · {conv.size_kb} KB
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Messages importés */}
          <div style={S.chatPane}>
            {!selectedImported ? (
              <div style={S.placeholder}>← Sélectionne une conversation</div>
            ) : (
              <>
                <div style={S.chatHeader}>
                  <div style={{ ...S.avatar, width: 36, height: 36, fontSize: 16, background: '#7c3aed' }}>
                    {(selectedImported.name || '?')[0].toUpperCase()}
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15 }}>{selectedImported.name}</div>
                    <div style={{ fontSize: 11, color: '#64748b' }}>
                      {selectedImported.message_count} messages
                    </div>
                  </div>
                </div>
                <div style={S.messagesArea}>
                  {loading && <p style={S.muted}>Chargement...</p>}
                  {importedMsgs.map((msg, i) => (
                    <div key={i} style={{ ...S.msgRow, justifyContent: msg.is_mine ? 'flex-end' : 'flex-start' }}>
                      {!msg.is_mine && (
                        <div style={S.avatarSmall}>{(msg.sender || '?')[0].toUpperCase()}</div>
                      )}
                      <div style={{ maxWidth: '70%' }}>
                        {!msg.is_mine && (
                          <div style={S.senderName}>{msg.sender}</div>
                        )}
                        <div style={{ ...S.bubble, ...(msg.is_mine ? S.bubbleMine : S.bubbleOther) }}>
                          {msg.text}
                        </div>
                        <div style={{ ...S.ts, textAlign: msg.is_mine ? 'right' : 'left' }}>
                          {msg.timestamp ? new Date(msg.timestamp).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}
                        </div>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────
const S = {
  container: { display: 'flex', flexDirection: 'column', gap: 0, height: '85vh' },

  header: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '12px 16px', background: '#0f172a',
    borderBottom: '1px solid #1e293b',
  },
  headerTitle: { fontWeight: 700, fontSize: 16, color: '#f1f5f9' },
  syncBadge: { fontSize: 12, color: '#64748b', marginLeft: 'auto' },
  refreshBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    fontSize: 16, color: '#64748b', padding: '4px 8px',
  },

  tabs: {
    display: 'flex', gap: 0,
    borderBottom: '1px solid #1e293b', background: '#0f172a',
  },
  tab: {
    background: 'none', border: 'none', color: '#64748b',
    fontSize: 13, padding: '10px 18px', cursor: 'pointer',
    display: 'flex', alignItems: 'center', gap: 6,
  },
  tabActive: { color: '#60a5fa', borderBottom: '2px solid #60a5fa' },
  countBadge: {
    background: '#1e3a5f', color: '#93c5fd',
    borderRadius: 10, padding: '1px 7px', fontSize: 11,
  },

  layout: {
    display: 'grid', gridTemplateColumns: '280px 1fr',
    flex: 1, overflow: 'hidden',
  },

  sidebar: {
    background: '#0f172a', borderRight: '1px solid #1e293b',
    overflowY: 'auto', padding: '10px 0',
  },
  searchInput: {
    width: 'calc(100% - 20px)', margin: '0 10px 10px',
    background: '#1e293b', border: '1px solid #334155',
    borderRadius: 8, padding: '7px 10px', color: '#f1f5f9',
    fontSize: 13, outline: 'none',
  },

  chatRow: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '10px 12px', cursor: 'pointer',
    transition: 'background .15s',
  },
  avatar: {
    width: 42, height: 42, borderRadius: '50%',
    background: '#1e3a5f', color: '#93c5fd',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 700, fontSize: 17, flexShrink: 0,
  },
  avatarSmall: {
    width: 28, height: 28, borderRadius: '50%',
    background: '#1e3a5f', color: '#93c5fd',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: 700, fontSize: 12, flexShrink: 0, alignSelf: 'flex-end',
  },
  chatInfo: { flex: 1, minWidth: 0 },
  chatMeta: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  chatName: { fontWeight: 600, fontSize: 13, color: '#e2e8f0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  chatTime: { fontSize: 11, color: '#64748b', flexShrink: 0, marginLeft: 4 },
  chatPreview: { fontSize: 12, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 },
  unreadBadge: {
    background: '#22c55e', color: '#fff', borderRadius: 10,
    padding: '1px 6px', fontSize: 11, fontWeight: 700, flexShrink: 0,
  },

  chatPane: {
    display: 'flex', flexDirection: 'column', background: '#0f172a', overflow: 'hidden',
  },
  chatHeader: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '10px 16px', borderBottom: '1px solid #1e293b',
    background: '#0f172a',
  },

  messagesArea: {
    flex: 1, padding: '16px', overflowY: 'auto',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  msgRow: { display: 'flex', alignItems: 'flex-end', gap: 6 },
  senderName: { fontSize: 11, color: '#60a5fa', marginBottom: 2, marginLeft: 4 },
  bubble: {
    padding: '8px 12px', borderRadius: 16,
    fontSize: 14, lineHeight: 1.4, wordBreak: 'break-word',
    maxWidth: '100%',
  },
  bubbleMine: {
    background: '#1d4ed8', color: '#fff',
    borderBottomRightRadius: 4,
  },
  bubbleOther: {
    background: '#1e293b', color: '#e2e8f0',
    borderBottomLeftRadius: 4,
  },
  ts: { fontSize: 10, color: '#475569', marginTop: 2, paddingLeft: 4, paddingRight: 4 },

  suggBox: {
    padding: '12px 16px', borderTop: '1px solid #1e293b', background: '#020617',
  },
  suggHeader: { fontSize: 12, color: '#64748b', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 },
  confBadge: { background: '#064e3b', color: '#34d399', borderRadius: 8, padding: '1px 7px', fontSize: 11 },
  suggText: {
    background: '#1e293b', padding: '10px 14px',
    borderRadius: 10, color: '#e2e8f0', fontSize: 14,
  },
  suggActions: { display: 'flex', gap: 8, marginTop: 10 },

  placeholder: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flex: 1, color: '#334155', fontSize: 14,
  },
  muted: { color: '#475569', fontSize: 13, padding: '8px 12px' },

  // Pages QR / offline
  card: {
    background: '#0f172a', borderRadius: 16, padding: 40,
    textAlign: 'center', border: '1px solid #1e293b', maxWidth: 400, margin: '40px auto',
  },
  bigIcon: { fontSize: 52, marginBottom: 16 },
  code: {
    display: 'block', background: '#1e293b', padding: '10px 16px',
    borderRadius: 8, color: '#93c5fd', fontSize: 13,
    fontFamily: 'monospace', margin: '0 auto',
  },
  btn: {
    background: '#1e293b', color: '#94a3b8',
    border: '1px solid #334155', borderRadius: 8,
    padding: '10px 18px', cursor: 'pointer', fontSize: 14,
  },
  btnGreen: {
    background: '#166534', color: '#86efac', border: 'none',
    borderRadius: 8, padding: '8px 16px', fontWeight: 600, cursor: 'pointer', fontSize: 13,
  },
  btnAlt: {
    background: '#1e3a5f', color: '#93c5fd', border: 'none',
    borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 13,
  },
  btnIgnore: {
    background: '#0f172a', color: '#f87171',
    border: '1px solid #7f1d1d', borderRadius: 8,
    padding: '8px 14px', cursor: 'pointer', fontSize: 13,
  },
  qrPulse: {
    width: 10, height: 10, background: '#22c55e', borderRadius: '50%',
    margin: '14px auto 0',
  },
}
