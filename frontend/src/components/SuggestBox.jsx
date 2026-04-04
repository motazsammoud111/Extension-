import { useState } from 'react'
import axios from 'axios'

const PERSON_TYPES = [
  { value: 'close_friend', label: '👊 Ami proche' },
  { value: 'family',       label: '👨‍👩‍👧 Famille' },
  { value: 'colleague',    label: '💼 Collègue' },
  { value: 'client',       label: '🤝 Client' },
  { value: 'unknown',      label: '❓ Inconnu' },
]

export default function SuggestBox({ api, profile, onRefresh }) {
  const [message, setMessage] = useState('')
  const [personType, setPersonType] = useState('close_friend')
  const [contextNote, setContextNote] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('')
  const [history, setHistory] = useState([])

  const noProfile = !profile || profile.total_messages_analyzed === 0

  async function suggest() {
    if (!message.trim()) return
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await axios.post(`${api}/suggest`, {
        message: message.trim(),
        person_type: personType,
        context_note: contextNote,
        history: history.slice(-6),
      })
      setResult(res.data)
      setHistory(h => [...h,
        { role: 'user', content: message },
        { role: 'assistant', content: res.data.response },
      ])
    } catch (e) {
      setError(e.response?.data?.detail || 'Erreur lors de la génération')
    } finally {
      setLoading(false)
    }
  }

  async function sendFeedback(rating) {
    if (!result?.response_id) return
    await axios.post(`${api}/feedback`, {
      response_id: result.response_id,
      rating,
      used: rating === 1,
    })
    onRefresh()
  }

  function copy(text, key) {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(''), 2000)
  }

  function useResponse(text) {
    copy(text, 'used')
    sendFeedback(1)
  }

  return (
    <div>
      <h2 style={s.sectionTitle}>💬 Générer une réponse dans ton style</h2>

      {noProfile && (
        <div style={s.warning}>
          ⚠️ Profil vide — importe d'abord des conversations dans l'onglet <strong>📥 Importer</strong>
        </div>
      )}

      {/* Input */}
      <div style={s.card}>
        <label style={s.label}>Message reçu</label>
        <textarea
          style={s.textarea}
          placeholder="Colle ici le message auquel tu veux répondre..."
          value={message}
          onChange={e => setMessage(e.target.value)}
          onKeyDown={e => e.ctrlKey && e.key === 'Enter' && suggest()}
          rows={4}
        />
        <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label style={s.label}>Type d'interlocuteur</label>
            <select
              style={s.select}
              value={personType}
              onChange={e => setPersonType(e.target.value)}
            >
              {PERSON_TYPES.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div style={{ flex: 2, minWidth: 220 }}>
            <label style={s.label}>Note de contexte (optionnel)</label>
            <input
              style={s.input}
              placeholder="ex: message urgent, on rigole, conversation pro..."
              value={contextNote}
              onChange={e => setContextNote(e.target.value)}
            />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
          <button style={s.btnPrimary} onClick={suggest} disabled={loading || !message.trim()}>
            {loading ? '⏳ Génération...' : '✨ Générer la réponse (Ctrl+Enter)'}
          </button>
          {history.length > 0 && (
            <button style={s.btnSecondary} onClick={() => { setHistory([]); setResult(null) }}>
              🗑 Réinitialiser
            </button>
          )}
        </div>
      </div>

      {error && <div style={s.error}>❌ {error}</div>}

      {/* Résultat */}
      {result && (
        <div style={s.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <span style={s.label}>✉️ Réponse principale</span>
            <span style={{ fontSize: 12, color: '#64748b' }}>
              Confiance : {Math.round(result.confidence * 100)}% • {result.model}
            </span>
          </div>

          <div style={s.responseBox}>
            <p style={{ fontSize: 16, lineHeight: 1.6 }}>{result.response}</p>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button style={s.btnGreen} onClick={() => useResponse(result.response)}>
              {copied === 'used' ? '✅ Copié !' : '📋 Utiliser (copier)'}
            </button>
            <button style={{ ...s.btnSecondary, color: '#4ade80' }}
              onClick={() => sendFeedback(1)}>👍 Bon style</button>
            <button style={{ ...s.btnSecondary, color: '#f87171' }}
              onClick={() => sendFeedback(-1)}>👎 Mauvais style</button>
          </div>

          {/* Alternatives */}
          {result.alternatives?.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <label style={s.label}>🔄 Alternatives</label>
              {result.alternatives.map((alt, i) => (
                <div key={i} style={{ ...s.altBox, marginTop: 10 }}>
                  <p style={{ fontSize: 14, color: '#cbd5e1' }}>{alt}</p>
                  <button style={s.btnSmall} onClick={() => copy(alt, `alt${i}`)}>
                    {copied === `alt${i}` ? '✅' : '📋 Copier'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Historique de conversation */}
      {history.length > 0 && (
        <div style={s.card}>
          <label style={s.label}>🧵 Fil de conversation ({history.length / 2} échanges)</label>
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {history.map((m, i) => (
              <div key={i} style={{
                ...s.historyMsg,
                alignSelf: m.role === 'user' ? 'flex-start' : 'flex-end',
                background: m.role === 'user' ? '#1e293b' : '#1e3a5f',
              }}>
                <span style={{ fontSize: 11, color: '#64748b' }}>
                  {m.role === 'user' ? '👤 Eux' : '🤖 Toi (twin)'}
                </span>
                <p style={{ fontSize: 14, marginTop: 4 }}>{m.content}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const s = {
  sectionTitle: { fontSize: 20, fontWeight: 700, color: '#f1f5f9', marginBottom: 20 },
  warning: {
    background: '#422006', border: '1px solid #92400e', borderRadius: 10,
    padding: '12px 16px', marginBottom: 16, color: '#fbbf24', fontSize: 14,
  },
  card: {
    background: '#1e293b', borderRadius: 12, padding: 20,
    border: '1px solid #334155', marginBottom: 16,
  },
  label: { fontSize: 12, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 1, fontWeight: 600 },
  textarea: {
    width: '100%', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 8, padding: '12px', color: '#e2e8f0', fontSize: 15,
    resize: 'vertical', marginTop: 8, fontFamily: 'inherit', outline: 'none',
  },
  input: {
    width: '100%', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 8, padding: '10px 12px', color: '#e2e8f0', fontSize: 14,
    marginTop: 8, fontFamily: 'inherit', outline: 'none',
  },
  select: {
    width: '100%', background: '#0f172a', border: '1px solid #334155',
    borderRadius: 8, padding: '10px 12px', color: '#e2e8f0', fontSize: 14,
    marginTop: 8, outline: 'none',
  },
  btnPrimary: {
    background: 'linear-gradient(135deg, #1d4ed8, #7c3aed)', color: '#fff',
    border: 'none', borderRadius: 8, padding: '12px 24px', fontSize: 15,
    fontWeight: 600, cursor: 'pointer',
  },
  btnSecondary: {
    background: '#0f172a', color: '#94a3b8',
    border: '1px solid #334155', borderRadius: 8, padding: '10px 16px',
    fontSize: 14, cursor: 'pointer',
  },
  btnGreen: {
    background: '#166534', color: '#86efac',
    border: 'none', borderRadius: 8, padding: '10px 20px',
    fontSize: 14, fontWeight: 600, cursor: 'pointer',
  },
  btnSmall: {
    background: '#1e293b', color: '#94a3b8',
    border: '1px solid #334155', borderRadius: 6, padding: '4px 10px',
    fontSize: 12, cursor: 'pointer', marginTop: 8,
  },
  responseBox: {
    background: '#0f172a', borderLeft: '3px solid #3b82f6',
    borderRadius: '0 8px 8px 0', padding: '16px', color: '#e2e8f0',
  },
  altBox: {
    background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: 12,
  },
  error: {
    background: '#450a0a', border: '1px solid #7f1d1d', borderRadius: 10,
    padding: '12px 16px', color: '#fca5a5', fontSize: 14, marginBottom: 16,
  },
  historyMsg: {
    maxWidth: '75%', padding: '10px 14px', borderRadius: 10,
    border: '1px solid #1e293b',
  },
}
