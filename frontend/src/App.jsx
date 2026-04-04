import { useState, useEffect } from 'react'
import axios from 'axios'
import Dashboard from './components/Dashboard.jsx'
import SuggestBox from './components/SuggestBox.jsx'
import WhatsAppPanel from './components/WhatsAppPanel.jsx'
import ImportPanel from './components/ImportPanel.jsx'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  const [tab, setTab] = useState('suggest')
  const [profile, setProfile] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [apiOnline, setApiOnline] = useState(false)

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 15000)
    return () => clearInterval(interval)
  }, [])

  async function loadData() {
    try {
      const [pRes, sRes] = await Promise.all([
        axios.get(`${API}/personality`),
        axios.get(`${API}/stats`),
      ])
      setProfile(pRes.data)
      setStats(sRes.data)
      setApiOnline(true)
    } catch {
      setApiOnline(false)
    } finally {
      setLoading(false)
    }
  }

  const tabs = [
    { id: 'suggest', label: '💬 Suggérer', desc: 'Répondre dans ton style' },
    { id: 'whatsapp', label: '📱 WhatsApp', desc: 'Connexion QR code' },
    { id: 'import', label: '📥 Importer', desc: 'Ajouter des conversations' },
    { id: 'dashboard', label: '📊 Profil', desc: 'Ton profil IA' },
  ]

  return (
    <div style={styles.root}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>🤖</span>
          <div>
            <div style={styles.title}>Digital Twin AI</div>
            <div style={styles.subtitle}>
              {profile?.name || 'Chargement...'} •{' '}
              {stats?.messages_analyzed || 0} messages appris
            </div>
          </div>
        </div>
        <div style={{
          ...styles.badge,
          background: apiOnline ? '#166534' : '#7f1d1d',
          color: apiOnline ? '#86efac' : '#fca5a5',
        }}>
          {apiOnline ? '● En ligne' : '● Hors ligne'}
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              ...styles.tab,
              ...(tab === t.id ? styles.tabActive : {}),
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={styles.content}>
        {!apiOnline && (
          <div style={styles.offlineBanner}>
            ⚠️ Backend hors ligne — lance <code>python backend/main.py</code> puis recharge
          </div>
        )}

        {loading ? (
          <div style={styles.center}>
            <div style={styles.spinner}>⏳</div>
            <p style={{ color: '#94a3b8', marginTop: 12 }}>Connexion au backend...</p>
          </div>
        ) : (
          <>
            {tab === 'suggest' && <SuggestBox api={API} profile={profile} onRefresh={loadData} />}
            {tab === 'whatsapp' && <WhatsAppPanel api={API} />}
            {tab === 'import' && <ImportPanel api={API} onRefresh={loadData} />}
            {tab === 'dashboard' && <Dashboard profile={profile} stats={stats} />}
          </>
        )}
      </div>
    </div>
  )
}

const styles = {
  root: { minHeight: '100vh', display: 'flex', flexDirection: 'column' },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '16px 24px',
    background: 'linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%)',
    borderBottom: '1px solid #1e293b',
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 14 },
  logo: { fontSize: 36 },
  title: { fontSize: 20, fontWeight: 700, color: '#f1f5f9' },
  subtitle: { fontSize: 13, color: '#64748b', marginTop: 2 },
  badge: {
    padding: '6px 14px', borderRadius: 20, fontSize: 13, fontWeight: 600,
  },
  tabs: {
    display: 'flex', gap: 4, padding: '12px 24px',
    background: '#0f172a', borderBottom: '1px solid #1e293b',
  },
  tab: {
    padding: '8px 20px', borderRadius: 8, border: 'none', cursor: 'pointer',
    fontSize: 14, fontWeight: 500,
    background: 'transparent', color: '#64748b',
    transition: 'all 0.15s',
  },
  tabActive: { background: '#1e40af', color: '#fff' },
  content: { flex: 1, padding: '24px', maxWidth: 900, margin: '0 auto', width: '100%' },
  offlineBanner: {
    background: '#422006', border: '1px solid #92400e', borderRadius: 10,
    padding: '12px 16px', marginBottom: 20, color: '#fbbf24', fontSize: 14,
  },
  center: { display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: 80 },
  spinner: { fontSize: 48, animation: 'spin 1s linear infinite' },
}
