import { useMemo, useState } from 'react'
import type { AgentTurn, CityState } from '../api'
import { formatBehaviorLabel } from '../ui'

interface Props {
  state: CityState
  logs: Record<string, AgentTurn[]>
}

interface AgentConsoleSpec {
  agentId: string
  behavior: string
}

function TurnCard({ turn }: { turn: AgentTurn }) {
  const [expanded, setExpanded] = useState(false)
  const ts = new Date(turn.ts * 1000).toLocaleTimeString()

  return (
    <article className="turn-card">
      <div className="turn-card__header">
        <div className="turn-card__meta">
          <span>{ts}</span>
          <span
            className="chip"
            style={{
              color: turn.ok ? '#7fd8a8' : '#ff8f8f',
              background: turn.ok ? 'rgba(38, 102, 69, 0.28)' : 'rgba(122, 37, 37, 0.28)',
              borderColor: turn.ok ? 'rgba(127, 216, 168, 0.24)' : 'rgba(255, 108, 103, 0.24)',
            }}
          >
            {turn.ok ? 'ok' : 'error'}
          </span>
          {turn.repair && <span className="chip chip--neutral">repair</span>}
        </div>
        <button onClick={() => setExpanded((value) => !value)} className="turn-card__toggle">
          {expanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      <div className="turn-card__decision">{turn.decision}</div>

      <div className="turn-card__preview">
        <span className="turn-card__label">prompt</span>
        <span>
          {expanded ? turn.prompt : turn.prompt.slice(0, 180) + (turn.prompt.length > 180 ? '…' : '')}
        </span>
      </div>

      <div className="turn-card__preview">
        <span className="turn-card__label">response</span>
        <span className={expanded ? 'turn-card__response turn-card__response--expanded' : 'turn-card__response'}>
          {turn.response || '(empty)'}
        </span>
      </div>

      {expanded && (
        <div className="turn-card__expanded">
          <div>
            <div className="detail-block__label">Full prompt</div>
            <pre className="json-block">{turn.prompt}</pre>
          </div>
          <div>
            <div className="detail-block__label">Full response</div>
            <pre className="json-block">{turn.response || '(empty)'}</pre>
          </div>
        </div>
      )}
    </article>
  )
}

function compareAgentIds(left: string, right: string) {
  if (left === 'mayor') return 1
  if (right === 'mayor') return -1

  const leftMatch = left.match(/^citizen-(\d+)$/)
  const rightMatch = right.match(/^citizen-(\d+)$/)
  if (leftMatch && rightMatch) return Number(leftMatch[1]) - Number(rightMatch[1])
  return left.localeCompare(right)
}

function buildAgentSpecs(state: CityState): AgentConsoleSpec[] {
  const ordered = Object.values(state.citizens)
    .sort((left, right) => compareAgentIds(left.citizen_id, right.citizen_id))
    .map((citizen) => ({
      agentId: citizen.citizen_id,
      behavior: citizen.behavior,
    }))

  ordered.push({ agentId: 'mayor', behavior: 'optimizer' })
  return ordered
}

export function AgentConsoles({ state, logs }: Props) {
  const agentSpecs = useMemo(() => buildAgentSpecs(state), [state])
  const [activeAgent, setActiveAgent] = useState('citizen-001')
  const totalTurns = Object.values(logs).reduce((sum, items) => sum + items.length, 0)
  const currentAgentId = agentSpecs.some((spec) => spec.agentId === activeAgent)
    ? activeAgent
    : (agentSpecs[0]?.agentId ?? '')
  const activeSpec = agentSpecs.find((spec) => spec.agentId === currentAgentId) ?? agentSpecs[0] ?? null
  const turns = [...(logs[activeSpec?.agentId ?? ''] ?? [])].reverse()

  return (
    <section className="panel consoles-panel">
      <div className="consoles-panel__header">
        <div>
          <div className="panel-kicker">Agent consoles</div>
          <h2 className="panel-title">Prompt and response traces</h2>
        </div>
        <div className="summary-card summary-card--narrow">
          <div className="summary-card__label">Captured turns</div>
          <div className="summary-card__value">{totalTurns}</div>
          <div className="summary-card__note">{agentSpecs.length} tracked agents</div>
        </div>
      </div>

      <div className="console-tabs" role="tablist" aria-label="Agent consoles">
        {agentSpecs.map((spec) => {
          const count = logs[spec.agentId]?.length ?? 0
          const isActive = currentAgentId === spec.agentId

          return (
            <button
              key={spec.agentId}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveAgent(spec.agentId)}
              className={`console-tab${isActive ? ' console-tab--active' : ''}`}
            >
              <span className="console-tab__title">{spec.agentId}</span>
              <span className="console-tab__meta">{formatBehaviorLabel(spec.behavior)}</span>
              {count > 0 && <span className="console-tab__count">{count}</span>}
            </button>
          )
        })}
      </div>

      <div className="console-focus">
        <div className="console-focus__header">
          {activeSpec && (
            <div className="console-focus__identity">
              <div className="console-focus__title">{activeSpec.agentId}</div>
              <div className="console-focus__meta">{formatBehaviorLabel(activeSpec.behavior)}</div>
            </div>
          )}

          <div className="console-focus__count">{turns.length} turns</div>
        </div>

        <div className="console-body">
          {turns.length === 0 ? (
            <span className="console-empty">
              No turns recorded yet for {activeSpec?.agentId ?? 'this agent'}.
            </span>
          ) : (
            turns.map((turn, index) => <TurnCard key={`${turn.ts}-${index}`} turn={turn} />)
          )}
        </div>
      </div>
    </section>
  )
}
