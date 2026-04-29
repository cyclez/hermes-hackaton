import type { MayorDecree } from '../api'

interface Props {
  decree: MayorDecree | null
}

const ACTION_COLORS: Record<string, string> = {
  SURVEIL: '#f97316',
  ARREST: '#ef4444',
  JAM_SERVER: '#eab308',
  BRIBE: '#a78bfa',
  RELEASE: '#22c55e',
  PARDON: '#22c55e',
}

export function MayorPanel({ decree }: Props) {
  return (
    <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, padding: 16, flexShrink: 0 }}>
      <h2 style={{ color: '#94a3b8', fontSize: 13, fontWeight: 600, margin: '0 0 12px', textTransform: 'uppercase', letterSpacing: 1 }}>
        Mayor
      </h2>

      {!decree ? (
        <p style={{ color: '#475569', fontSize: 13, margin: 0 }}>No decrees yet</p>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{
              background: ACTION_COLORS[decree.action] ?? '#475569',
              color: '#fff',
              borderRadius: 4,
              padding: '2px 10px',
              fontSize: 12,
              fontWeight: 700,
            }}>{decree.action}</span>
            {decree.targets.map(t => (
              <span key={t} style={{ color: '#cbd5e1', fontSize: 12, background: '#334155', borderRadius: 3, padding: '1px 6px' }}>{t}</span>
            ))}
          </div>

          <p style={{ color: '#94a3b8', fontSize: 12, margin: '0 0 8px', lineHeight: 1.5 }}>
            {decree.rationale}
          </p>

          {decree.duration_seconds > 0 && (
            <div style={{ color: '#64748b', fontSize: 11 }}>duration: {decree.duration_seconds}s</div>
          )}
          {decree.created_at && (
            <div style={{ color: '#475569', fontSize: 10, marginTop: 4 }}>
              {new Date(decree.created_at).toLocaleTimeString()}
            </div>
          )}
        </>
      )}
    </div>
  )
}
