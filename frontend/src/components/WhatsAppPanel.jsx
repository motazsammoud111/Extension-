import { useState, useEffect } from 'react'
import axios from 'axios'

const WA_BRIDGE = import.meta.env.VITE_WA_BRIDGE_URL || 'http://localhost:3001'

export default function WhatsAppPanel({ api }) {
  // Bridge state
  const [status, setStatus] = useState('disconnected')
  const [qr, setQr] = useState(null)
  const [bridgeChats, setBridgeChats] = useState([])
  const [selectedBridgeChat, setSelectedBridgeChat] = useState(null)
  const [bridgeMessages, setBridgeMessages] = useState([])
  const [suggestion, setSuggestion] = useState(null)
  
  // Imported conversations state
  const [importedConvs, setImportedConvs] = useState([])
  const [selectedImported, setSelectedImported] = useState(null)
  const [importedMessages, setImportedMessages] = useState([])
  const [activeTab, setActiveTab] = useState('bridge')
  
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    checkStatus()
    const interval = setInterval(checkStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (status === 'connected') loadBridgeChats()
  }, [status])

  useEffect(() => {
    if (activeTab === 'imported') loadImportedConversations()
  }, [activeTab])

  useEffect(() => {
    if (selectedBridgeChat && activeTab === 'bridge') loadBridgeMessages()
  }, [selectedBridgeChat])

  useEffect(() => {
    if (selectedImported && activeTab === 'imported') loadImportedMessages()
  }, [selectedImported])

  // Bridge functions
  async function checkStatus() {
    try {
      const res = await axios.get(`${WA_BRIDGE}/status`)
      setStatus(res.data.status)
      if (res.data.qr) setQr(res.data.qr)
    } catch {
      setStatus('bridge_offline')
    }
  }

  async function startConnection() {
    await axios.post(`${WA_BRIDGE}/connect`)
    setStatus('qr')
  }

  async function loadBridgeChats() {
    try {
      const res = await axios.get(`${WA_BRIDGE}/chats`)
      setBridgeChats(res.data.chats || [])
    } catch (err) {
      console.error(err)
    }
  }

  async function loadBridgeMessages() {
    if (!selectedBridgeChat) return
    setLoading(true)
    try {
      const res = await axios.get(`${WA_BRIDGE}/messages/${selectedBridgeChat.id}`)
      setBridgeMessages(res.data.messages || [])
      const lastIncoming = (res.data.messages || []).filter(m => !m.fromMe).slice(-1)[0]
      if (lastIncoming) await getSuggestion(lastIncoming.body)
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  async function getSuggestion(msgText) {
    if (!msgText) return
    try {
      const res = await axios.post(`${api}/suggest`, {
        message: msgText,
        person_type: 'close_friend',
      })
      setSuggestion(res.data)
    } catch {}
  }

  async function sendResponse(text) {
    if (!selectedBridgeChat) return
    try {
      await axios.post(`${WA_BRIDGE}/send`, {
        chatId: selectedBridgeChat.id,
        message: text,
      })
      setSuggestion(null)
      await loadBridgeMessages()
    } catch {
      alert('Erreur envoi message')
    }
  }

  // Imported functions
  async function loadImportedConversations() {
    try {
      const res = await axios.get(`${api}/conversations`)
      setImportedConvs(res.data.conversations || [])
    } catch (err) {
      console.error(err)
    }
  }

  async function loadImportedMessages() {
    if (!selectedImported) return
    setLoading(true)
    try {
      const res = await axios.get(`${api}/conversations/${encodeURIComponent(selectedImported.name)}`)
      setImportedMessages(res.data.messages || [])
    } catch (err) {
      console.error(err)
    }
    setLoading(false)
  }

  // Render
  if (status === 'bridge_offline') {
    return (
      <div style={styles.card}>
        <div style={styles.bigIcon}>🔌</div>
        <h3 style={{ color: '#f87171' }}>Bridge hors ligne</h3>
        <p>Lance : <code>cd whatsapp-bridge && npm start</code></p>
        <button style={styles.btn} onClick={checkStatus}>🔄 Vérifier</button>
      </div>
    )
  }

  if (status === 'disconnected') {
    return (
      <div style={styles.card}>
        <div style={styles.bigIcon}>📱</div>
        <h3>Connecter ton WhatsApp</h3>
        <p>Le twin pourra lire tes messages et suggérer des réponses en direct.</p>
        <button style={styles.btnGreen} onClick={startConnection}>📲 Scanner le QR code</button>
      </div>
    )
  }

  if (status === 'qr' && qr) {
    return (
      <div style={{ ...styles.card, textAlign: 'center' }}>
        <p>Ouvre WhatsApp → Appareils connectés → Connecter un appareil</p>
        <img src={qr} alt="QR" style={{ width: 250, height: 250, background: '#fff', padding: 8, borderRadius: 12 }} />
        <div style={styles.qrDot} />
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>📱 WhatsApp connecté ✅</h2>
      <div style={styles.tabs}>
        <button onClick={() => setActiveTab('bridge')} style={{ ...styles.tab, ...(activeTab === 'bridge' && styles.activeTab) }}>💬 Messages en direct</button>
        <button onClick={() => setActiveTab('imported')} style={{ ...styles.tab, ...(activeTab === 'imported' && styles.activeTab) }}>📚 Historique importé ({importedConvs.length})</button>
      </div>

      {activeTab === 'bridge' && (
        <div style={styles.twoColumns}>
          <div style={styles.chatList}>
            <div style={styles.listHeader}>Conversations récentes</div>
            {bridgeChats.map(chat => (
              <div key={chat.id} onClick={() => setSelectedBridgeChat(chat)} style={{ ...styles.chatCard, background: selectedBridgeChat?.id === chat.id ? '#1e3a5f' : '#0f172a' }}>
                <div style={styles.chatName}>{chat.name}</div>
                <div style={styles.chatPreview}>{chat.lastMessage?.slice(0, 50)}</div>
              </div>
            ))}
          </div>
          <div style={styles.conversation}>
            {!selectedBridgeChat ? (
              <div style={styles.placeholder}>← Sélectionne une conversation</div>
            ) : (
              <>
                <div style={styles.messagesArea}>
                  {loading && <p>Chargement...</p>}
                  {bridgeMessages.map((msg, i) => (
                    <div key={i} style={{ ...styles.messageBubble, alignSelf: msg.fromMe ? 'flex-end' : 'flex-start' }}>
                      <div style={styles.bubbleContent}>{msg.body}</div>
                      <div style={styles.timestamp}>{new Date(msg.timestamp * 1000).toLocaleTimeString()}</div>
                    </div>
                  ))}
                </div>
                {suggestion && (
                  <div style={styles.suggestionCard}>
                    <div style={styles.suggestionHeader}>🤖 Réponse suggérée ({Math.round(suggestion.confidence * 100)}%)</div>
                    <div style={styles.suggestionText}>{suggestion.response}</div>
                    <div style={styles.suggestionActions}>
                      <button style={styles.btnGreen} onClick={() => sendResponse(suggestion.response)}>✅ Envoyer</button>
                      {suggestion.alternatives?.[0] && <button style={styles.btnAlt} onClick={() => sendResponse(suggestion.alternatives[0])}>🔄 Alternative</button>}
                      <button style={styles.btnIgnore} onClick={() => setSuggestion(null)}>✕ Ignorer</button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {activeTab === 'imported' && (
        <div style={styles.twoColumns}>
          <div style={styles.chatList}>
            <div style={styles.listHeader}>Toutes les conversations importées</div>
            {importedConvs.length === 0 && <p style={styles.muted}>Aucune conversation importée. Va dans l'onglet Importer.</p>}
            {importedConvs.map(conv => (
              <div key={conv.name} onClick={() => setSelectedImported(conv)} style={{ ...styles.chatCard, background: selectedImported?.name === conv.name ? '#1e3a5f' : '#0f172a' }}>
                <div style={styles.chatName}>{conv.name}</div>
                <div style={styles.chatPreview}>{conv.message_count} messages</div>
              </div>
            ))}
          </div>
          <div style={styles.conversation}>
            {!selectedImported ? (
              <div style={styles.placeholder}>← Sélectionne une conversation</div>
            ) : (
              <div style={styles.messagesArea}>
                {loading && <p>Chargement...</p>}
                {importedMessages.map((msg, i) => (
                  <div key={i} style={{ ...styles.messageBubble, alignSelf: msg.is_mine ? 'flex-end' : 'flex-start' }}>
                    <div style={styles.bubbleContent}>{msg.text}</div>
                    <div style={styles.timestamp}>{new Date(msg.timestamp).toLocaleString()}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

const styles = {
  container: { display: 'flex', flexDirection: 'column', gap: 20 },
  title: { fontSize: 20, fontWeight: 700, color: '#f1f5f9' },
  tabs: { display: 'flex', gap: 10, borderBottom: '1px solid #334155' },
  tab: { background: 'none', border: 'none', color: '#94a3b8', fontSize: 14, padding: '8px 16px', cursor: 'pointer' },
  activeTab: { color: '#60a5fa', borderBottom: '2px solid #60a5fa' },
  twoColumns: { display: 'grid', gridTemplateColumns: '300px 1fr', gap: 20 },
  chatList: { background: '#1e293b', borderRadius: 12, padding: 16, border: '1px solid #334155', height: '70vh', overflowY: 'auto' },
  listHeader: { fontSize: 12, color: '#64748b', textTransform: 'uppercase', marginBottom: 12 },
  chatCard: { padding: '12px', borderRadius: 10, marginBottom: 8, cursor: 'pointer' },
  chatName: { fontWeight: 600, fontSize: 14 },
  chatPreview: { fontSize: 12, color: '#94a3b8', marginTop: 4 },
  conversation: { background: '#1e293b', borderRadius: 12, border: '1px solid #334155', display: 'flex', flexDirection: 'column', height: '70vh' },
  messagesArea: { flex: 1, padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 },
  messageBubble: { maxWidth: '70%', display: 'flex', flexDirection: 'column' },
  bubbleContent: { background: '#0f172a', padding: '8px 12px', borderRadius: 12, fontSize: 14 },
  timestamp: { fontSize: 10, color: '#64748b', marginTop: 2, marginLeft: 8 },
  suggestionCard: { borderTop: '1px solid #334155', padding: 16, background: '#0f172a' },
  suggestionHeader: { fontSize: 12, color: '#64748b', marginBottom: 8 },
  suggestionText: { background: '#1e293b', padding: '12px', borderRadius: 8, color: '#e2e8f0' },
  suggestionActions: { display: 'flex', gap: 10, marginTop: 12 },
  placeholder: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b' },
  card: { background: '#1e293b', borderRadius: 12, padding: 32, textAlign: 'center', border: '1px solid #334155' },
  bigIcon: { fontSize: 48, marginBottom: 16 },
  muted: { color: '#64748b', fontSize: 14 },
  btn: { background: '#0f172a', color: '#94a3b8', border: '1px solid #334155', borderRadius: 8, padding: '10px 18px', cursor: 'pointer' },
  btnGreen: { background: '#166534', color: '#86efac', border: 'none', borderRadius: 8, padding: '10px 18px', fontWeight: 600, cursor: 'pointer' },
  btnAlt: { background: '#1e3a5f', color: '#93c5fd', border: 'none', borderRadius: 8, padding: '10px 18px', cursor: 'pointer' },
  btnIgnore: { background: '#0f172a', color: '#f87171', border: '1px solid #7f1d1d', borderRadius: 8, padding: '10px 18px', cursor: 'pointer' },
  qrDot: { width: 10, height: 10, background: '#22c55e', borderRadius: '50%', margin: '12px auto 0', animation: 'pulse 1.5s infinite' },
}