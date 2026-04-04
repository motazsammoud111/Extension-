import { useState, useRef } from 'react'
import axios from 'axios'

export default function ImportPanel({ api, onRefresh }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState([])
  const inputRef = useRef()

  async function uploadFile(file) {
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['txt', 'json'].includes(ext)) {
      setResults(r => [...r, { file: file.name, error: 'Format non supporté (.txt ou .json uniquement)' }])
      return
    }
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await axios.post(`${api}/import`, form)
      setResults(r => [...r, { ...res.data, success: true }])
      onRefresh()
    } catch (e) {
      setResults(r => [...r, { file: file.name, error: e.response?.data?.detail || 'Erreur' }])
    } finally {
      setUploading(false)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    const files = [...e.dataTransfer.files]
    files.forEach(uploadFile)
  }

  return (
    <div>
      <h2 style={s.title}>📥 Importer des conversations</h2>

      {/* Guide export */}
      <div style={s.card}>
        <h3 style={{ color: '#93c5fd', marginBottom: 16, fontSize: 15 }}>
          📋 Comment exporter tes conversations ?
        </h3>
        <div style={s.grid}>
          {[
            {
              icon: '💚', name: 'WhatsApp',
              steps: ['Ouvre un chat → ⋮ Menu', 'Plus → Exporter la discussion', 'Choisir "Sans médias"', 'Envoie le .txt à toi-même'],
            },
            {
              icon: '✈️', name: 'Telegram',
              steps: ['Paramètres → Avancés', 'Exporter les données Telegram', 'Sélectionne Messages → JSON', 'Place result.json ici'],
            },
            {
              icon: '📸', name: 'Instagram',
              steps: ['Paramètres → Sécurité', 'Données & accès → Télécharger', 'Messages → Format JSON', 'Place message_1.json ici'],
            },
          ].map(src => (
            <div key={src.name} style={s.sourceCard}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>{src.icon}</div>
              <div style={{ fontWeight: 600, marginBottom: 10, color: '#e2e8f0' }}>{src.name}</div>
              {src.steps.map((step, i) => (
                <div key={i} style={s.step}>
                  <span style={s.stepNum}>{i + 1}</span>
                  <span style={{ fontSize: 13, color: '#94a3b8' }}>{step}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Drop zone */}
      <div
        style={{
          ...s.dropZone,
          ...(dragging ? s.dropZoneActive : {}),
          ...(uploading ? s.dropZoneUploading : {}),
        }}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.json"
          multiple
          style={{ display: 'none' }}
          onChange={e => [...e.target.files].forEach(uploadFile)}
        />
        <div style={{ fontSize: 40, marginBottom: 12 }}>
          {uploading ? '⏳' : dragging ? '📂' : '📁'}
        </div>
        <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 6 }}>
          {uploading ? 'Analyse en cours...' : 'Glisse tes fichiers ici'}
        </div>
        <div style={{ color: '#64748b', fontSize: 13 }}>
          {uploading ? 'Patience...' : 'ou clique pour choisir • .txt (WhatsApp) ou .json (Telegram/Instagram)'}
        </div>
      </div>

      {/* Résultats */}
      {results.length > 0 && (
        <div style={s.card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>Résultats d'import</span>
            <button style={s.clearBtn} onClick={() => setResults([])}>Effacer</button>
          </div>
          {results.map((r, i) => (
            <div key={i} style={{
              ...s.resultRow,
              borderColor: r.success ? '#166534' : '#7f1d1d',
              background: r.success ? '#0d1f0d' : '#1c0a0a',
            }}>
              {r.success ? (
                <>
                  <span style={{ color: '#4ade80' }}>✅ {r.file}</span>
                  <span style={{ color: '#86efac' }}>
                    +{r.my_messages} messages • {r.source} • {r.participation_rate}% participation
                  </span>
                </>
              ) : (
                <>
                  <span style={{ color: '#f87171' }}>❌ {r.file}</span>
                  <span style={{ color: '#fca5a5' }}>{r.error}</span>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={s.tip}>
        💡 Astuce : plus tu importes de conversations, plus le twin te ressemble. Vise 200+ messages.
      </div>
    </div>
  )
}

const s = {
  title: { fontSize: 20, fontWeight: 700, color: '#f1f5f9', marginBottom: 20 },
  card: {
    background: '#1e293b', borderRadius: 12, padding: 20,
    border: '1px solid #334155', marginBottom: 16,
  },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 },
  sourceCard: {
    background: '#0f172a', borderRadius: 10, padding: 16,
    border: '1px solid #1e293b',
  },
  step: { display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 },
  stepNum: {
    background: '#1e3a5f', color: '#93c5fd', borderRadius: '50%',
    width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 11, fontWeight: 700, flexShrink: 0,
  },
  dropZone: {
    border: '2px dashed #334155', borderRadius: 12, padding: '40px 24px',
    textAlign: 'center', cursor: 'pointer', marginBottom: 16,
    transition: 'all 0.2s',
  },
  dropZoneActive: { borderColor: '#3b82f6', background: '#0f1f3d' },
  dropZoneUploading: { borderColor: '#a855f7', background: '#1a0f2e', cursor: 'wait' },
  resultRow: {
    display: 'flex', flexDirection: 'column', gap: 4,
    padding: '10px 14px', borderRadius: 8, border: '1px solid',
    marginBottom: 8, fontSize: 13,
  },
  clearBtn: {
    background: 'transparent', color: '#64748b', border: 'none',
    fontSize: 12, cursor: 'pointer',
  },
  tip: {
    background: '#1a1a2e', border: '1px solid #1e3a5f', borderRadius: 10,
    padding: '12px 16px', color: '#60a5fa', fontSize: 13,
  },
}
