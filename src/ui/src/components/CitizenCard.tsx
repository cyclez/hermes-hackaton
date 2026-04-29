import type { Citizen } from '../api'

const MODE_COLORS: Record<string, string> = {
  MINE: '#3b82f6',
  SYNC: '#22c55e',
  SLEEP: '#6b7280',
}

const STATUS_COLORS: Record<string, string> = {
  JAILED: '#ef4444',
  SURVEILLED: '#f97316',
  JAMMED: '#eab308',
}

function StatBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8' }}>
        <span>{label}</span>
        <span>{Math.round(value)}</span>
      </div>
      <div style={{ background: '#374151', borderRadius: 2, height: 4 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
    </div>
  )
}

interface Props {
  citizen: Citizen
  now: number
}

export function CitizenCard({ citizen, now }: Props) {
  const modeColor = MODE_COLORS[citizen.mode] ?? '#6b7280'
  const cooldownLeft = Math.max(0, citizen.action_cooldown_until - now)

  return (
    <div style={{
      background: '#1e293b',
      border: '1px solid #334155',
      borderRadius: 8,
      padding: 14,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ color: '#e2e8f0', fontWeight: 600, fontSize: 13 }}>{citizen.citizen_id}</span>
        <span style={{
          background: modeColor,
          color: '#fff',
          borderRadius: 4,
          padding: '1px 7px',
          fontSize: 11,
          fontWeight: 700,
        }}>{citizen.mode}</span>
      </div>

      <div style={{ color: '#64748b', fontSize: 11 }}>
        {citizen.behavior} {citizen.queued_mode && <span style={{ color: '#94a3b8' }}>→ {citizen.queued_mode}</span>}
      </div>

      {citizen.statuses.length > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {citizen.statuses.map((s, i) => (
            <span key={i} style={{
              background: STATUS_COLORS[s.effect] ?? '#475569',
              color: '#fff',
              borderRadius: 3,
              padding: '1px 6px',
              fontSize: 10,
              fontWeight: 600,
            }}>{s.effect}</span>
          ))}
        </div>
      )}

      <div style={{ marginTop: 4 }}>
        <StatBar label="STK" value={citizen.stk} max={9999} color="#818cf8" />
        <StatBar label="SHIVA" value={citizen.shiva} max={100} color="#34d399" />
        <StatBar label="TRACE" value={citizen.trace} max={100} color="#f87171" />
      </div>

      {cooldownLeft > 0 && (
        <div style={{ color: '#94a3b8', fontSize: 11 }}>
          cooldown: {cooldownLeft.toFixed(0)}s
        </div>
      )}
    </div>
  )
}
