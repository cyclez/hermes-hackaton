import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { DecisionLogAttempt, DecisionLogEntry, DecisionLogRun } from '../api'
import { fetchDecisionLogs, fetchDecisionLogRuns } from '../api'
import { formatBehaviorLabel, formatClockTime, formatDateTime, formatTokenLabel, hexToRgba, isRecord } from '../ui'

function formatRunOptionLabel(run: DecisionLogRun) {
  return `${run.game_id.slice(0, 8)}…${run.game_id.slice(-4)} (${run.entry_count})`
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="json-block">
      {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
    </pre>
  )
}

function DetailBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="detail-block">
      <div className="detail-block__label">{label}</div>
      {children}
    </div>
  )
}

function AttemptCard({ attempt }: { attempt: DecisionLogAttempt }) {
  return (
    <details className="attempt-card">
      <summary className="attempt-card__summary">
        <span>attempt {attempt.attempt}</span>
        <span>{attempt.ok ? 'ok' : 'invalid'}</span>
        {attempt.repair && <span>repair</span>}
        {attempt.elapsed_seconds !== null && <span>{attempt.elapsed_seconds.toFixed(2)}s</span>}
      </summary>
      <div className="attempt-card__body">
        <DetailBlock label="Prompt">
          <JsonBlock value={attempt.prompt} />
        </DetailBlock>
        <DetailBlock label="Response">
          <JsonBlock value={attempt.response || '(empty)'} />
        </DetailBlock>
        <DetailBlock label="Attempt metadata">
          <JsonBlock
            value={{
              validation_error: attempt.validation_error,
              usage: attempt.usage,
              api_calls: attempt.api_calls,
              elapsed_seconds: attempt.elapsed_seconds,
            }}
          />
        </DetailBlock>
      </div>
    </details>
  )
}

function StatusMetric({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: string
}) {
  return (
    <div className="status-metric">
      <div className="status-metric__label">{label}</div>
      <div className="status-metric__value" style={tone ? { color: tone } : undefined}>
        {value}
      </div>
    </div>
  )
}

function EntryCard({ entry }: { entry: DecisionLogEntry }) {
  const situation = isRecord(entry.situation) ? entry.situation : {}
  const observation = isRecord(situation.observation) ? situation.observation : {}
  const privateObservation = isRecord(observation.private) ? observation.private : {}
  const snapshot = isRecord(situation.status_snapshot) ? situation.status_snapshot : privateObservation
  const citizenSnapshots = Array.isArray(situation.citizen_snapshots)
    ? situation.citizen_snapshots.filter(isRecord)
    : []
  const recentEvidence = Array.isArray(situation.recent_evidence) ? situation.recent_evidence : []
  const recentActions = Array.isArray(situation.recent_actions) ? situation.recent_actions : []
  const finalPayload = isRecord(entry.final.payload) ? entry.final.payload : {}
  const finalAction =
    entry.role === 'citizen'
      ? String(entry.final.payload.action ?? entry.final.payload.kind ?? 'unknown')
      : String(entry.final.payload.action ?? 'unknown')
  const roleColor = entry.role === 'citizen' ? '#58b8ff' : '#ffb457'
  const actionColor = entry.final.ok ? '#7fd8a8' : '#ff6c67'
  const rationale = typeof finalPayload.rationale === 'string' ? finalPayload.rationale : entry.summary
  const repairCount = entry.attempts.filter((attempt) => attempt.repair).length
  const statuses = Array.isArray(snapshot.statuses) ? snapshot.statuses.map(String) : []
  const allowedActions = Array.isArray(observation.allowed_actions) ? observation.allowed_actions.length : 0

  return (
    <article className="panel decision-entry">
      <div className="decision-entry__header">
        <div className="decision-entry__identity">
          <div className="decision-entry__title">
            <span
              className="chip"
              style={{
                color: roleColor,
                background: hexToRgba(roleColor, 0.14),
                borderColor: hexToRgba(roleColor, 0.34),
              }}
            >
              {entry.role}
            </span>
            <strong>{entry.agent_id}</strong>
            <span className="decision-entry__behavior">{formatBehaviorLabel(entry.behavior)}</span>
            <span
              className="chip"
              style={{
                color: actionColor,
                background: hexToRgba(actionColor, 0.12),
                borderColor: hexToRgba(actionColor, 0.28),
              }}
            >
              {formatTokenLabel(finalAction)}
            </span>
          </div>
          <div className="decision-entry__meta">
            <span>{formatDateTime(entry.ts)}</span>
            <span>{entry.model}</span>
            <span>{entry.attempts.length} attempt{entry.attempts.length === 1 ? '' : 's'}</span>
            {repairCount > 0 && <span>{repairCount} repair</span>}
          </div>
        </div>

        <div
          className="decision-entry__result"
          style={{
            color: entry.final.ok ? '#7fd8a8' : '#ff8f8f',
            background: entry.final.ok ? 'rgba(38, 102, 69, 0.32)' : 'rgba(122, 37, 37, 0.32)',
            borderColor: entry.final.ok ? 'rgba(127, 216, 168, 0.28)' : 'rgba(255, 108, 103, 0.28)',
          }}
        >
          {entry.final.ok ? 'OK' : 'ERROR'}
        </div>
      </div>

      <div className="decision-entry__stats">
        {entry.role === 'citizen' ? (
          <>
            <StatusMetric label="Mode" value={String(snapshot.mode ?? 'n/a')} />
            <StatusMetric label="STK" value={String(snapshot.stk ?? 'n/a')} />
            <StatusMetric label="SHIVA" value={String(snapshot.shiva ?? 'n/a')} />
            <StatusMetric
              label="Trace"
              value={String(snapshot.trace ?? 'n/a')}
              tone={Number(snapshot.trace) >= 40 ? '#ffb457' : undefined}
            />
            <StatusMetric label="Cooldown" value={String(snapshot.action_cooldown_remaining ?? '0')} />
            <StatusMetric label="Allowed actions" value={String(allowedActions)} />
          </>
        ) : (
          <>
            <StatusMetric label="Heat" value={String(situation.heat ?? 'n/a')} />
            <StatusMetric label="Game hour" value={String(situation.game_hour ?? 'n/a')} />
            <StatusMetric label="Citizens" value={String(citizenSnapshots.length)} />
            <StatusMetric label="Evidence" value={String(recentEvidence.length)} />
            <StatusMetric label="Recent actions" value={String(recentActions.length)} />
            <StatusMetric label="Issued at" value={formatClockTime(entry.ts)} />
          </>
        )}
      </div>

      {statuses.length > 0 && (
        <div className="decision-entry__chips">
          {statuses.map((status) => (
            <span key={status} className="chip chip--neutral">
              {status}
            </span>
          ))}
        </div>
      )}

      {entry.role === 'mayor' && citizenSnapshots.length > 0 && (
        <div className="decision-entry__chips">
          {citizenSnapshots.slice(0, 6).map((row) => (
            <span key={String(row.citizen_id)} className="chip chip--neutral">
              {String(row.citizen_id)} · {String(row.mode)} · trace {String(row.trace)}
            </span>
          ))}
        </div>
      )}

      <div className="decision-entry__summary">
        <div className="decision-entry__summary-label">Rationale</div>
        <div>{rationale}</div>
      </div>

      <div className="decision-entry__details">
        <DetailBlock label="Situation JSON">
          <JsonBlock value={entry.situation} />
        </DetailBlock>
        <DetailBlock label="Final payload">
          <JsonBlock value={entry.final.payload} />
        </DetailBlock>
      </div>

      <div className="decision-entry__attempts">
        {entry.attempts.map((attempt) => (
          <AttemptCard key={`${entry.log_id}-${attempt.attempt}`} attempt={attempt} />
        ))}
      </div>
    </article>
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

    void poll()
    const intervalId = setInterval(() => {
      void poll()
    }, 3000)

    return () => {
      cancelled = true
      clearInterval(intervalId)
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

  const selectedRun = runs.find((run) => run.game_id === selectedGameId)

  return (
    <div className="log-page">
      <div className="panel log-page__header">
        <div>
          <div className="panel-kicker">Decision logs</div>
          <h1 className="log-page__title">Runtime decision inspector</h1>
          <div className="panel-copy">Durable prompt, response, and validation traces for citizen and Mayor turns.</div>
        </div>
        <a href="/" className="button button--secondary">Back to control room</a>
      </div>

      <div className="log-page__layout">
        <aside className="log-page__sidebar">
          <section className="panel app-nav-card">
            <div>
              <div className="panel-kicker">Filters</div>
              <div className="panel-title panel-title--small">Select run and scope</div>
              <div className="panel-copy">Narrow the live trace without changing the stored backend data.</div>
            </div>
          </section>

          <section className="panel citizen-section">
            <div className="field-grid">
              <label className="field">
                <span className="field__label">Run</span>
                <select value={selectedGameId} onChange={(event) => setSelectedGameId(event.target.value)} className="control">
                  {runs.length === 0 && <option value="">No runs yet</option>}
                  {runs.map((run) => (
                    <option key={run.game_id} value={run.game_id}>
                      {formatRunOptionLabel(run)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span className="field__label">Role</span>
                <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} className="control">
                  <option value="">all</option>
                  <option value="citizen">citizen</option>
                  <option value="mayor">mayor</option>
                </select>
              </label>

              <label className="field">
                <span className="field__label">Agent</span>
                <select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)} className="control">
                  <option value="">all</option>
                  {agentOptions.map((agentId) => (
                    <option key={agentId} value={agentId}>{agentId}</option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          <section className="panel citizen-section">
            <div className="panel-kicker">Run summary</div>
            <div className="summary-grid">
              <div className="summary-card">
                <div className="summary-card__label">Visible entries</div>
                <div className="summary-card__value">{entries.length}</div>
                <div className="summary-card__note">filtered results</div>
              </div>
              <div className="summary-card">
                <div className="summary-card__label">Agents</div>
                <div className="summary-card__value">{agentOptions.length}</div>
                <div className="summary-card__note">present in current view</div>
              </div>
              <div className="summary-card">
                <div className="summary-card__label">Run count</div>
                <div className="summary-card__value">{runs.length}</div>
                <div className="summary-card__note">stored on disk</div>
              </div>
              <div className="summary-card">
                <div className="summary-card__label">Updated</div>
                <div className="summary-card__value">
                  {selectedRun?.updated_at ? formatClockTime(selectedRun.updated_at) : 'n/a'}
                </div>
                <div className="summary-card__note">page polls every 3s</div>
              </div>
            </div>
          </section>

          <section className="panel citizen-section">
            <div className="panel-kicker">Current selection</div>
            <div className="panel-copy">{selectedGameId || 'No run selected'}</div>
            <div className="decision-entry__chips">
              <span className="chip chip--neutral">{roleFilter || 'all roles'}</span>
              <span className="chip chip--neutral">{agentFilter || 'all agents'}</span>
              <span className="chip chip--neutral">
                {selectedRun ? `${selectedRun.entry_count} stored entries` : 'awaiting run'}
              </span>
            </div>
            {selectedRun?.updated_at && (
              <div className="panel-copy panel-copy--tight">Last updated {formatDateTime(selectedRun.updated_at)}</div>
            )}
          </section>
        </aside>

        <section className="log-page__results">
          {error && (
            <div className="panel panel--alert">
              <div className="panel-kicker">Read error</div>
              <div className="panel-copy">{error}</div>
            </div>
          )}

          {entries.length === 0 ? (
            <div className="panel panel--empty">
              <div className="panel-kicker">No trace data</div>
              <div className="panel-title panel-title--small">No decision logs match the current selection.</div>
              <div className="panel-copy">Switch runs or broaden the filters to inspect stored turns.</div>
            </div>
          ) : (
            entries.map((entry) => <EntryCard key={entry.log_id} entry={entry} />)
          )}
        </section>
      </div>
    </div>
  )
}
