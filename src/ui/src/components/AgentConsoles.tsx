import { useState } from 'react'
import type { AgentTurn } from '../api'
import { formatBehaviorLabel } from '../ui'

interface Props {
  logs: Record<string, AgentTurn[]>
}

const AGENT_IDS = ['citizen-001', 'citizen-002', 'citizen-003', 'citizen-004', 'citizen-005', 'mayor']
const BEHAVIOR: Record<string, string> = {
  'citizen-001': 'aggressive',
  'citizen-002': 'cautious',
  'citizen-003': 'opportunistic',
  'citizen-004': 'stealth_first',
  'citizen-005': 'resource_maximizer',
  mayor: 'optimizer',
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

export function AgentConsoles({ logs }: Props) {
  const [activeTab, setActiveTab] = useState('citizen-001')
  const turns = [...(logs[activeTab] ?? [])].reverse()
  const totalTurns = Object.values(logs).reduce((sum, items) => sum + items.length, 0)

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
          <div className="summary-card__note">across all agents</div>
        </div>
      </div>

      <div className="console-tabs">
        {AGENT_IDS.map((id) => {
          const count = logs[id]?.length ?? 0
          const isActive = activeTab === id
          return (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`console-tab${isActive ? ' console-tab--active' : ''}`}
            >
              <span className="console-tab__title">{id}</span>
              <span className="console-tab__meta">{formatBehaviorLabel(BEHAVIOR[id])}</span>
              {count > 0 && <span className="console-tab__count">{count}</span>}
            </button>
          )
        })}
      </div>

      <div className="console-body">
        {turns.length === 0 ? (
          <span className="console-empty">No turns recorded yet for {activeTab}.</span>
        ) : (
          turns.map((turn, index) => <TurnCard key={`${turn.ts}-${index}`} turn={turn} />)
        )}
      </div>
    </section>
  )
}
