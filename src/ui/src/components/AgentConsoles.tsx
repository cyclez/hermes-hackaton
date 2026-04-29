import { useState } from 'react'
import type { AgentTurn } from '../api'

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
  'mayor': 'optimizer',
}

function TurnCard({ turn }: { turn: AgentTurn }) {
  const [expanded, setExpanded] = useState(false)
  const ts = new Date(turn.ts * 1000).toLocaleTimeString()

  return (
    <div style={{
      fontFamily: 'monospace',
      fontSize: 11,
      borderBottom: '1px solid #1e293b',
      paddingBottom: 10,
      marginBottom: 10,
    }}>
      {/* Turn header */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
        <span style={{ color: '#475569', flexShrink: 0 }}>{ts}</span>
        <span style={{
          background: turn.ok ? '#14532d' : '#450a0a',
          color: turn.ok ? '#86efac' : '#fca5a5',
          borderRadius: 3,
          padding: '0 6px',
          fontSize: 10,
          fontWeight: 700,
        }}>{turn.ok ? '✓ OK' : '✗ ERR'}</span>
        {turn.repair && (
          <span style={{ color: '#f59e0b', fontSize: 10, fontWeight: 700 }}>REPAIR</span>
        )}
        <span style={{ color: '#94a3b8', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {turn.decision}
        </span>
        <button
          onClick={() => setExpanded(e => !e)}
          style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: 11, padding: 0 }}
        >{expanded ? '▲' : '▼'}</button>
      </div>

      {/* Prompt */}
      <div style={{ marginBottom: 4 }}>
        <span style={{ color: '#22d3ee', marginRight: 6 }}>▶ PROMPT</span>
        <span style={{ color: '#64748b' }}>
          {expanded ? turn.prompt : turn.prompt.slice(0, 120) + (turn.prompt.length > 120 ? '…' : '')}
        </span>
      </div>

      {/* Response */}
      <div>
        <span style={{ color: '#a3e635', marginRight: 6 }}>◀ RESPONSE</span>
        <span style={{ color: '#cbd5e1', whiteSpace: expanded ? 'pre-wrap' : 'nowrap', overflow: 'hidden', display: 'block', maxWidth: '100%', textOverflow: expanded ? 'unset' : 'ellipsis' }}>
          {turn.response || '(empty)'}
        </span>
      </div>
    </div>
  )
}

export function AgentConsoles({ logs }: Props) {
  const [activeTab, setActiveTab] = useState('citizen-001')
  const turns = [...(logs[activeTab] ?? [])].reverse()

  return (
    <div style={{
      background: '#0d1117',
      border: '1px solid #1e293b',
      borderRadius: 8,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      marginTop: 16,
    }}>
      {/* Tab bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid #1e293b',
        overflowX: 'auto',
        flexShrink: 0,
      }}>
        {AGENT_IDS.map(id => {
          const count = logs[id]?.length ?? 0
          const isActive = activeTab === id
          return (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                background: isActive ? '#1e293b' : 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #60a5fa' : '2px solid transparent',
                color: isActive ? '#e2e8f0' : '#475569',
                padding: '8px 12px',
                fontSize: 11,
                fontFamily: 'monospace',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
            >
              {id}
              <span style={{ color: '#334155', fontSize: 10, marginLeft: 4 }}>
                {BEHAVIOR[id]}
              </span>
              {count > 0 && (
                <span style={{
                  background: '#1e3a8a',
                  color: '#93c5fd',
                  borderRadius: 8,
                  padding: '0 5px',
                  fontSize: 9,
                  marginLeft: 5,
                }}>{count}</span>
              )}
            </button>
          )
        })}
      </div>

      {/* Console body */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 14px',
        minHeight: 200,
        maxHeight: 340,
      }}>
        {turns.length === 0 ? (
          <span style={{ color: '#334155', fontFamily: 'monospace', fontSize: 11 }}>
            No turns yet for {activeTab}…
          </span>
        ) : (
          turns.map((t, i) => <TurnCard key={i} turn={t} />)
        )}
      </div>
    </div>
  )
}
