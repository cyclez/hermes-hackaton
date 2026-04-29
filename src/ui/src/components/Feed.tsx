import type { GameEvent } from '../api'

const KIND_COLORS: Record<string, string> = {
  citizen_action:   '#60a5fa',
  mode_change:      '#2dd4bf',
  citizen_jailed:   '#ef4444',
  citizen_released: '#22c55e',
  mayor_decree:     '#fb923c',
  invalid_decision: '#f87171',
  heat_change:      '#a78bfa',
  game_start:       '#facc15',
  game_end:         '#facc15',
  server_tick:      '#334155',
}

const KIND_TEXT: Record<string, string> = {
  server_tick: '#4b5563',
}

interface Props {
  label: string
  events: GameEvent[]
  accent: string
}

export function Feed({ label, events, accent }: Props) {
  return (
    <div style={{
      background: '#1e293b',
      border: '1px solid #334155',
      borderRadius: 8,
      padding: 14,
      display: 'flex',
      flexDirection: 'column',
      flex: 1,        // take equal share of parent height
      minHeight: 0,   // allow shrinking below content size
    }}>
      <div style={{
        fontSize: 11,
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: 1,
        color: accent,
        marginBottom: 10,
      }}>{label}</div>

      <div style={{
        overflowY: 'auto',
        flex: 1,          // fills the remaining space inside the card
        minHeight: 0,     // required for overflow-y to work inside flex
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}>
        {events.length === 0 && (
          <span style={{ color: '#374151', fontSize: 12 }}>No events yet…</span>
        )}
        {events.map(e => (
          <div key={e.event_id} style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
            <span style={{
              color: KIND_COLORS[e.kind] ?? '#94a3b8',
              fontSize: 9,
              fontWeight: 700,
              textTransform: 'uppercase',
              minWidth: 80,
              paddingTop: 2,
              flexShrink: 0,
              letterSpacing: 0.5,
            }}>{e.kind.replace(/_/g, ' ')}</span>
            <span style={{
              color: KIND_TEXT[e.kind] ?? '#cbd5e1',
              fontSize: 11,
              lineHeight: 1.4,
            }}>{e.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
