import { useMemo, useState } from 'react'
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
}

type ActivityTab = 'citizen' | 'mayor' | 'system'

interface Props {
  citizenEvents: GameEvent[]
  mayorEvents: GameEvent[]
  systemEvents: GameEvent[]
}

function readString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function getCitizenOutcome(event: GameEvent) {
  if (event.kind !== 'citizen_action') return null

  return {
    citizenId: readString(event.payload.citizen_id) ?? 'citizen',
    action: readString(event.payload.action),
    caught: readBoolean(event.payload.caught),
  }
}

function formatActivityMessage(event: GameEvent) {
  const outcome = getCitizenOutcome(event)
  if (!outcome) return event.message

  const action = outcome.action ? formatTokenLabel(outcome.action) : 'action'
  if (outcome.caught === true) return `${outcome.citizenId} was caught on ${action}.`
  if (outcome.caught === false) return `${outcome.citizenId} slipped through on ${action}.`
  return event.message
}

export function ActivityPanel({ citizenEvents, mayorEvents, systemEvents }: Props) {
  const tabs = useMemo(
    () => [
      { id: 'citizen' as const, label: 'Citizen', accent: '#58b8ff', events: citizenEvents },
      { id: 'mayor' as const, label: 'Mayor', accent: '#ffb457', events: mayorEvents },
      { id: 'system' as const, label: 'System', accent: '#8ea3bb', events: systemEvents },
    ],
    [citizenEvents, mayorEvents, systemEvents],
  )
  const recentOutcomes = useMemo(
    () =>
      citizenEvents
        .map((event) => ({ event, outcome: getCitizenOutcome(event) }))
        .filter((item) => item.outcome?.caught !== null)
        .slice(0, 4),
    [citizenEvents],
  )

  const [activeTab, setActiveTab] = useState<ActivityTab>('citizen')
  const active = tabs.find((tab) => tab.id === activeTab) ?? tabs[0]
  const panelStyle = {
    ['--activity-accent' as string]: active.accent,
  } as CSSProperties

  return (
    <section className="panel activity-panel" style={panelStyle}>
      <div className="activity-panel__header">
        <div>
          <div className="panel-kicker">Activity</div>
          <div className="panel-title panel-title--small">{active.label}</div>
          <div className="panel-copy">Single event rail. Internal scroll stays here, not across the whole page.</div>
        </div>
        <a href="/decision-logs" className="button button--secondary activity-panel__link">
          Logs
        </a>
      </div>

      <div className="activity-tabs" role="tablist" aria-label="Activity feeds">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(tab.id)}
              className={`activity-tab${isActive ? ' activity-tab--active' : ''}`}
              style={
                isActive
                  ? {
                      color: tab.accent,
                      borderColor: `${tab.accent}55`,
                      background: `${tab.accent}18`,
                    }
                  : undefined
              }
            >
              <span className="activity-tab__label">{tab.label}</span>
              <span className="activity-tab__count">{tab.events.length}</span>
            </button>
          )
        })}
      </div>

      {recentOutcomes.length > 0 && (
        <div className="activity-verdicts">
          {recentOutcomes.map(({ event, outcome }) => {
            if (!outcome) return null
            const verdictTone = outcome.caught ? '#ff6c67' : '#7fd8a8'

            return (
              <article key={`${event.event_id}-verdict`} className="activity-verdict">
                <div className="activity-verdict__meta">
                  <span>{outcome.citizenId}</span>
                  {outcome.action && <span>{formatTokenLabel(outcome.action)}</span>}
                </div>
                <span
                  className="activity-verdict__status"
                  style={{
                    color: verdictTone,
                    background: `${verdictTone}18`,
                    borderColor: `${verdictTone}40`,
                  }}
                >
                  {outcome.caught ? 'caught' : 'missed'}
                </span>
              </article>
            )
          })}
        </div>
      )}

      <div className="activity-list">
        {active.events.length === 0 ? (
          <div className="activity-empty">
            No {active.label.toLowerCase()} activity yet.
          </div>
        ) : (
          active.events.map((event) => {
            const outcome = getCitizenOutcome(event)
            const verdictTone = outcome?.caught ? '#ff6c67' : '#7fd8a8'

            return (
              <article key={event.event_id} className="activity-item">
                <div className="activity-item__topline">
                  <span className="activity-item__meta">T{event.tick}</span>
                  <span className="activity-item__meta">H{event.game_hour.toFixed(1)}</span>
                  <span
                    className="activity-item__kind"
                    style={{ color: KIND_COLORS[event.kind] ?? active.accent }}
                  >
                    {formatTokenLabel(event.kind)}
                  </span>
                </div>

                {(outcome?.action || outcome?.caught !== null) && (
                  <div className="activity-item__summary">
                    {outcome?.action && (
                      <span className="activity-item__action">
                        {formatTokenLabel(outcome.action)}
                      </span>
                    )}
                    {outcome?.caught !== null && (
                      <span
                        className="activity-item__verdict"
                        style={{
                          color: verdictTone,
                          background: `${verdictTone}18`,
                          borderColor: `${verdictTone}40`,
                        }}
                      >
                        {outcome?.caught ? 'caught' : 'missed'}
                      </span>
                    )}
                  </div>
                )}

                <div className="activity-item__message">{formatActivityMessage(event)}</div>
              </article>
            )
          })
        )}
      </div>
    </section>
  )
}
