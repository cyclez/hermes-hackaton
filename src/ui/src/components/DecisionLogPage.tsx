import type { CSSProperties } from 'react'
import { useEffect, useMemo, useState } from 'react'
import type { DecisionLogAttempt, DecisionLogEntry, DecisionLogRun } from '../api'
import { fetchDecisionLogs, fetchDecisionLogRuns } from '../api'

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre style={{
      margin: 0,
      padding: 12,
      background: '#0f172a',
      border: '1px solid #1e293b',
      borderRadius: 6,
      color: '#cbd5e1',
      fontSize: 11,
      overflowX: 'auto',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word',
      fontFamily: 'monospace',
    }}>
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function AttemptCard({ attempt }: { attempt: DecisionLogAttempt }) {
  return (
    <details style={{
      background: '#111827',
      border: '1px solid #1f2937',
      borderRadius: 6,
      padding: '10px 12px',
    }}>
      <summary style={{ cursor: 'pointer', color: '#e2e8f0', fontSize: 12 }}>
        attempt {attempt.attempt} · {attempt.ok ? 'ok' : 'invalid'}{attempt.repair ? ' · repair' : ''}
        {attempt.elapsed_seconds !== null ? ` · ${attempt.elapsed_seconds.toFixed(2)}s` : ''}
      </summary>
      <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
        <div>
          <div style={{ color: '#22d3ee', fontSize: 11, marginBottom: 6 }}>Prompt</div>
          <JsonBlock value={attempt.prompt} />
        </div>
        <div>
          <div style={{ color: '#a3e635', fontSize: 11, marginBottom: 6 }}>Response</div>
          <JsonBlock value={attempt.response} />
        </div>
        <div>
          <div style={{ color: '#94a3b8', fontSize: 11, marginBottom: 6 }}>Attempt metadata</div>
          <JsonBlock value={{
            validation_error: attempt.validation_error,
            usage: attempt.usage,
            api_calls: attempt.api_calls,
            elapsed_seconds: attempt.elapsed_seconds,
          }} />
        </div>
      </div>
    </details>
  )
}

function CitizenStatusRow({ entry }: { entry: DecisionLogEntry }) {
  const snapshot = (entry.situation?.status_snapshot ?? {}) as Record<string, unknown>
  const statuses = Array.isArray(snapshot.statuses) ? snapshot.statuses.join(', ') : 'none'
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, color: '#94a3b8', fontSize: 12 }}>
      <span>mode: <strong style={{ color: '#e2e8f0' }}>{String(snapshot.mode ?? 'n/a')}</strong></span>
      <span>statuses: <strong style={{ color: '#e2e8f0' }}>{statuses || 'none'}</strong></span>
      <span>stk: <strong style={{ color: '#e2e8f0' }}>{String(snapshot.stk ?? 'n/a')}</strong></span>
      <span>shiva: <strong style={{ color: '#e2e8f0' }}>{String(snapshot.shiva ?? 'n/a')}</strong></span>
      <span>trace: <strong style={{ color: '#e2e8f0' }}>{String(snapshot.trace ?? 'n/a')}</strong></span>
      <span>cooldown: <strong style={{ color: '#e2e8f0' }}>{String(snapshot.action_cooldown_remaining ?? 'n/a')}</strong></span>
    </div>
  )
}

function MayorStatusRow({ entry }: { entry: DecisionLogEntry }) {
  const situation = entry.situation as Record<string, unknown>
  const citizenSnapshots = Array.isArray(situation.citizen_snapshots) ? situation.citizen_snapshots as Array<Record<string, unknown>> : []
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, color: '#94a3b8', fontSize: 12 }}>
        <span>heat: <strong style={{ color: '#e2e8f0' }}>{String(situation.heat ?? 'n/a')}</strong></span>
        <span>game hour: <strong style={{ color: '#e2e8f0' }}>{String(situation.game_hour ?? 'n/a')}</strong></span>
        <span>citizens: <strong style={{ color: '#e2e8f0' }}>{citizenSnapshots.length}</strong></span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {citizenSnapshots.map((row) => (
          <span
            key={String(row.citizen_id)}
            style={{
              background: '#1f2937',
              borderRadius: 999,
              padding: '4px 8px',
              color: '#cbd5e1',
              fontSize: 11,
              fontFamily: 'monospace',
            }}
          >
            {String(row.citizen_id)} · {String(row.mode)} · stk={String(row.stk)} · shiva={String(row.shiva)} · trace={String(row.trace)}
          </span>
        ))}
      </div>
    </div>
  )
}

function EntryCard({ entry }: { entry: DecisionLogEntry }) {
  const finalAction =
    entry.role === 'citizen'
      ? String(entry.final.payload.action ?? entry.final.payload.kind ?? 'unknown')
      : String(entry.final.payload.action ?? 'unknown')

  return (
    <div style={{
      background: '#111827',
      border: '1px solid #1f2937',
      borderRadius: 8,
      padding: 16,
      display: 'grid',
      gap: 12,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <div>
          <div style={{ color: '#e2e8f0', fontSize: 14, fontWeight: 700 }}>
            {entry.agent_id} · {entry.behavior} → {finalAction}
          </div>
          <div style={{ color: '#64748b', fontSize: 11 }}>
            {new Date(entry.ts * 1000).toLocaleString()} · {entry.model}
          </div>
        </div>
        <div style={{
          color: entry.final.ok ? '#86efac' : '#fca5a5',
          background: entry.final.ok ? '#14532d' : '#450a0a',
          borderRadius: 999,
          padding: '4px 10px',
          fontSize: 11,
          fontWeight: 700,
          flexShrink: 0,
        }}>
          {entry.final.ok ? 'OK' : 'ERROR'}
        </div>
      </div>

      {entry.role === 'citizen' ? <CitizenStatusRow entry={entry} /> : <MayorStatusRow entry={entry} />}

      <div style={{ color: '#cbd5e1', fontSize: 12 }}>{entry.summary}</div>

      <details>
        <summary style={{ cursor: 'pointer', color: '#93c5fd', fontSize: 12 }}>Situation JSON</summary>
        <div style={{ marginTop: 10 }}>
          <JsonBlock value={entry.situation} />
        </div>
      </details>

      <details>
        <summary style={{ cursor: 'pointer', color: '#93c5fd', fontSize: 12 }}>Final payload</summary>
        <div style={{ marginTop: 10 }}>
          <JsonBlock value={entry.final.payload} />
        </div>
      </details>

      <div style={{ display: 'grid', gap: 10 }}>
        {entry.attempts.map((attempt) => (
          <AttemptCard key={`${entry.log_id}-${attempt.attempt}`} attempt={attempt} />
        ))}
      </div>
    </div>
  )
}

export function DecisionLogPage() {
  const [runs, setRuns] = useState<DecisionLogRun[]>([])
  const [selectedGameId, setSelectedGameId] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [agentFilter, setAgentFilter] = useState('')
  const [entries, setEntries] = useState<DecisionLogEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      try {
        const runPayload = await fetchDecisionLogRuns()
        if (cancelled) return
        setRuns(runPayload.runs)

        const nextGameId =
          selectedGameId ||
          runPayload.current_game_id ||
          runPayload.runs[0]?.game_id ||
          ''

        if (!selectedGameId && nextGameId) {
          setSelectedGameId(nextGameId)
        }

        if (!nextGameId) {
          setEntries([])
          setError(null)
          return
        }

        const logEntries = await fetchDecisionLogs({
          gameId: nextGameId,
          limit: 300,
          role: roleFilter || undefined,
          agentId: agentFilter || undefined,
        })
        if (cancelled) return
        setEntries(logEntries)
        setError(null)
      } catch (err) {
        if (cancelled) return
        setError(String(err))
      }
    }

    poll()
    const id = setInterval(poll, 3000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [selectedGameId, roleFilter, agentFilter])

  const agentOptions = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const entry of entries) {
      if (!seen.has(entry.agent_id)) {
        seen.add(entry.agent_id)
        out.push(entry.agent_id)
      }
    }
    return out
  }, [entries])

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0f172a',
      color: '#e2e8f0',
      fontFamily: 'system-ui, sans-serif',
      padding: '20px 24px 32px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>Decision Logs</h1>
          <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>
            Durable per-run disk logs for citizen and Mayor decisions
          </div>
        </div>
        <a
          href="/"
          style={{
            color: '#93c5fd',
            textDecoration: 'none',
            border: '1px solid #1d4ed8',
            borderRadius: 6,
            padding: '8px 12px',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          ← Back to home
        </a>
      </div>

      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 12,
        marginBottom: 18,
        alignItems: 'center',
      }}>
        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
          Run
          <select value={selectedGameId} onChange={(e) => setSelectedGameId(e.target.value)} style={selectStyle}>
            {runs.map((run) => (
              <option key={run.game_id} value={run.game_id}>
                {run.game_id} ({run.entry_count})
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
          Role
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} style={selectStyle}>
            <option value="">all</option>
            <option value="citizen">citizen</option>
            <option value="mayor">mayor</option>
          </select>
        </label>

        <label style={{ display: 'grid', gap: 4, fontSize: 12 }}>
          Agent
          <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} style={selectStyle}>
            <option value="">all</option>
            {agentOptions.map((agentId) => (
              <option key={agentId} value={agentId}>{agentId}</option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <div style={{
          marginBottom: 16,
          background: '#450a0a',
          border: '1px solid #7f1d1d',
          color: '#fecaca',
          borderRadius: 8,
          padding: 12,
          fontSize: 12,
        }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gap: 14 }}>
        {entries.length === 0 ? (
          <div style={{
            background: '#111827',
            border: '1px solid #1f2937',
            borderRadius: 8,
            padding: 16,
            color: '#64748b',
            fontSize: 13,
          }}>
            No decision logs yet for this run.
          </div>
        ) : (
          entries.map((entry) => <EntryCard key={entry.log_id} entry={entry} />)
        )}
      </div>
    </div>
  )
}

const selectStyle: CSSProperties = {
  background: '#111827',
  color: '#e2e8f0',
  border: '1px solid #334155',
  borderRadius: 6,
  padding: '8px 10px',
  minWidth: 220,
}
