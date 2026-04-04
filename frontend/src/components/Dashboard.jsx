export default function Dashboard({ profile, stats }) {
  if (!profile) return <div style={{ color: '#64748b' }}>Chargement du profil...</div>

  const quality = getQuality(profile.total_messages_analyzed)

  return (
    <div>
      <h2 style={s.title}>📊 Profil de personnalité — {profile.name}</h2>

      {/* Stats cards */}
      <div style={s.grid4}>
        {[
          { label: 'Messages analysés', value: profile.total_messages_analyzed, icon: '💬', color: '#3b82f6' },
          { label: 'Longueur moyenne', value: `${profile.avg_message_length?.toFixed(1)} mots`, icon: '📏', color: '#8b5cf6' },
          { label: 'Usage emojis', value: `${Math.round((profile.emoji_usage_rate || 0) * 100)}%`, icon: '😀', color: '#f59e0b' },
          { label: 'Version profil', value: `v${profile.version}`, icon: '🔖', color: '#10b981' },
        ].map(card => (
          <div key={card.label} style={{ ...s.statCard, borderColor: card.color + '44' }}>
            <div style={{ fontSize: 28 }}>{card.icon}</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: card.color, marginTop: 8 }}>{card.value}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* Qualité du profil */}
      <div style={s.card}>
        <div style={s.label}>Qualité du profil d'apprentissage</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 12 }}>
          <div style={s.qualityBadge(quality.color)}>{quality.emoji} {quality.level}</div>
          <div style={{ flex: 1 }}>
            <div style={s.progressBar}>
              <div style={{ ...s.progressFill, width: `${quality.pct}%`, background: quality.color }} />
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 6 }}>{quality.advice}</div>
          </div>
        </div>
      </div>

      <div style={s.grid2}>
        {/* Ton & style */}
        <div style={s.card}>
          <div style={s.label}>Ton & Style</div>
          <div style={s.bigBadge}>{profile.dominant_tone || 'informel'}</div>
          <div style={s.row}>
            <span style={s.tag(profile.uses_slang)}>Argot {profile.uses_slang ? '✓' : '✗'}</span>
            <span style={s.tag(profile.uses_abbreviations)}>Abréviations {profile.uses_abbreviations ? '✓' : '✗'}</span>
          </div>
        </div>

        {/* Sources */}
        <div style={s.card}>
          <div style={s.label}>Sources de données</div>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(profile.sources || []).length === 0 ? (
              <span style={{ color: '#64748b', fontSize: 14 }}>Aucune source importée</span>
            ) : profile.sources.map(src => (
              <div key={src} style={s.sourceRow}>
                <span>{src === 'whatsapp' ? '💚' : src === 'telegram' ? '✈️' : '📸'}</span>
                <span style={{ textTransform: 'capitalize', fontWeight: 500 }}>{src}</span>
                <span style={{ color: '#64748b', fontSize: 12 }}>
                  {stats?.messages_by_source?.[src] || 0} msgs
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Vocabulaire */}
      <div style={s.card}>
        <div style={s.label}>🔤 Mots fréquents</div>
        <div style={s.tagCloud}>
          {(profile.top_words || []).slice(0, 30).map(([word, count]) => (
            <span key={word} style={{
              ...s.wordTag,
              fontSize: Math.max(11, Math.min(18, 10 + count / 2)),
              opacity: 0.6 + Math.min(count / 20, 0.4),
            }}>
              {word} <span style={{ color: '#475569', fontSize: 10 }}>{count}</span>
            </span>
          ))}
        </div>
      </div>

      {/* Emojis */}
      {profile.top_emojis?.length > 0 && (
        <div style={s.card}>
          <div style={s.label}>😀 Emojis favoris</div>
          <div style={{ ...s.tagCloud, fontSize: 24, marginTop: 10 }}>
            {profile.top_emojis.slice(0, 15).map(([emoji, count]) => (
              <span key={emoji} title={`${count} fois`} style={{ cursor: 'default' }}>
                {emoji}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Expressions typiques */}
      {profile.typical_expressions?.length > 0 && (
        <div style={s.card}>
          <div style={s.label}>💬 Expressions typiques</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
            {profile.typical_expressions.slice(0, 15).map((expr, i) => (
              <span key={i} style={s.exprTag}>"{expr}"</span>
            ))}
          </div>
        </div>
      )}

      {/* Stats DB */}
      {stats && (
        <div style={s.card}>
          <div style={s.label}>📈 Statistiques d'utilisation</div>
          <div style={s.grid4} >
            {[
              { k: 'Réponses générées', v: stats.responses_generated },
              { k: 'Réponses utilisées', v: stats.responses_used },
              { k: 'Confiance moyenne', v: `${Math.round((stats.avg_confidence || 0) * 100)}%` },
              { k: 'Feedbacks 👍', v: stats.ratings?.good || 0 },
            ].map(item => (
              <div key={item.k} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#e2e8f0' }}>{item.v}</div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{item.k}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function getQuality(n) {
  if (!n || n < 10) return { level: 'Insuffisant', emoji: '⚠️', color: '#ef4444', pct: 5, advice: 'Importe au moins 50 messages pour commencer.' }
  if (n < 50)  return { level: 'Débutant', emoji: '🌱', color: '#f59e0b', pct: 20, advice: `${50 - n} messages supplémentaires pour passer au niveau suivant.` }
  if (n < 200) return { level: 'Bon', emoji: '👍', color: '#3b82f6', pct: 50, advice: `${200 - n} messages pour un profil excellent.` }
  if (n < 500) return { level: 'Excellent', emoji: '🔥', color: '#8b5cf6', pct: 80, advice: `${500 - n} messages pour atteindre le niveau Expert.` }
  return { level: 'Expert', emoji: '⭐', color: '#10b981', pct: 100, advice: 'Profil expert — le twin est très fidèle à ton style !' }
}

const s = {
  title: { fontSize: 20, fontWeight: 700, color: '#f1f5f9', marginBottom: 20 },
  label: { fontSize: 11, color: '#64748b', textTransform: 'uppercase', letterSpacing: 1, fontWeight: 600 },
  card: { background: '#1e293b', borderRadius: 12, padding: 20, border: '1px solid #334155', marginBottom: 16 },
  grid4: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 16 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 0 },
  statCard: {
    background: '#1e293b', borderRadius: 12, padding: '20px 16px',
    border: '1px solid', textAlign: 'center',
  },
  progressBar: { height: 8, background: '#0f172a', borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 4, transition: 'width 0.5s' },
  qualityBadge: (color) => ({
    padding: '6px 14px', borderRadius: 20, fontSize: 14, fontWeight: 700,
    background: color + '22', color, border: `1px solid ${color}44`, whiteSpace: 'nowrap',
  }),
  bigBadge: {
    fontSize: 20, fontWeight: 700, color: '#818cf8', marginTop: 12, marginBottom: 12,
    textTransform: 'capitalize',
  },
  row: { display: 'flex', gap: 8, flexWrap: 'wrap' },
  tag: (active) => ({
    padding: '4px 10px', borderRadius: 6, fontSize: 12,
    background: active ? '#1e3a5f' : '#1e293b',
    color: active ? '#60a5fa' : '#475569',
    border: `1px solid ${active ? '#1e40af' : '#334155'}`,
  }),
  sourceRow: {
    display: 'flex', alignItems: 'center', gap: 10,
    padding: '8px 12px', background: '#0f172a', borderRadius: 8, fontSize: 14,
  },
  tagCloud: { display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  wordTag: {
    padding: '4px 10px', background: '#0f172a', borderRadius: 6,
    color: '#93c5fd', border: '1px solid #1e3a5f',
  },
  exprTag: {
    padding: '6px 12px', background: '#1a1a2e', borderRadius: 8,
    color: '#a78bfa', fontSize: 13, border: '1px solid #2d1f6e',
  },
}
