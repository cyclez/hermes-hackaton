import type { CSSProperties } from 'react'
import type { GameEvent } from '../api'
import { formatTokenLabel } from '../ui'

const KIND_COLORS: Record<string, string> = {
  citizen_action: '#58b8ff',
  mode_change: '#4cd2b7',
  citizen_jailed: '#ff6c67',
  citizen_released: '#7fd8a8',
  mayor_decree: '#ffb457',
  invalid_decision: '#ff8f8f',
  heat_change: '#b0a0ff',
  game_start: '#e8d075',
  game_end: '#e8d075',
  server_tick: '#8ea3bb',
}

interface Props {
  label: string
  events: GameEvent[]
  accent: string
}

export function Feed({ label, events, accent }: Props) {
  const feedStyle = {
    ['--feed-accent' as string]: accent,
  } as CSSProperties

  return (
    <section className="panel feed-panel" style={feedStyle}>
      <div className="feed-panel__header">
        <div>
          <div className="panel-kicker">Live feed</div>
          <div className="panel-title panel-title--small">{label}</div>
        </div>
        <span className="chip" style={{ color: accent, borderColor: `${accent}55` }}>
          {events.length}
        </span>
      </div>

      <div className="feed-list">
        {events.length === 0 && (
          <span className="feed-empty">No events yet.</span>
        )}
        {events.map((event) => (
          <div key={event.event_id} className="feed-item">
            <div className="feed-item__meta">
              <span>T{event.tick}</span>
              <span>H{event.game_hour.toFixed(1)}</span>
            </div>
            <span
              className="feed-item__kind"
              style={{ color: KIND_COLORS[event.kind] ?? accent }}
            >
              {formatTokenLabel(event.kind)}
            </span>
            <span className="feed-item__message">{event.message}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
