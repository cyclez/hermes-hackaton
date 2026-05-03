import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { CityState, TrainingStatus } from '../api'
import { restartServer, stopServer } from '../api'
import { hexToRgba } from '../ui'

interface Props {
  state: CityState
  serverTick: number
  lastLlmAt: number | null
  onRestart?: () => void
  onStop?: () => void
  serverStopped?: boolean
}

function PulseDot({ active, color }: { active: boolean; color: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: color,
        opacity: active ? 1 : 0.28,
        boxShadow: active ? `0 0 0 6px ${hexToRgba(color, 0.12)}` : 'none',
        transition: 'opacity 0.15s, box-shadow 0.15s',
        flexShrink: 0,
      }}
    />
  )
}

function TickIndicator({ label, tick, color }: { label: string; tick: number; color: string }) {
  const [lit, setLit] = useState(false)
  const prev = useRef(tick)

  useEffect(() => {
    if (tick !== prev.current) {
      prev.current = tick
      setLit(true)
      const timeout = setTimeout(() => setLit(false), 300)
      return () => clearTimeout(timeout)
    }
  }, [tick])

  return (
    <div className="live-indicator">
      <PulseDot active={lit} color={color} />
      <span className="live-indicator__label">{label}</span>
      <span className="live-indicator__value" style={{ color: lit ? color : '#d7e1ed' }}>
        {tick}
      </span>
    </div>
  )
}

function LlmIndicator({ lastLlmAt }: { lastLlmAt: number | null }) {
  const [lit, setLit] = useState(false)
  const prev = useRef(lastLlmAt)
  const [clock, setClock] = useState(() => Date.now())

  useEffect(() => {
    if (lastLlmAt !== null && lastLlmAt !== prev.current) {
      prev.current = lastLlmAt
      setLit(true)
      const timeout = setTimeout(() => setLit(false), 800)
      return () => clearTimeout(timeout)
    }
  }, [lastLlmAt])

  useEffect(() => {
    if (lastLlmAt === null) return

    const intervalId = setInterval(() => {
      setClock(Date.now())
    }, 1000)

    return () => clearInterval(intervalId)
  }, [lastLlmAt])

  const ago =
    lastLlmAt === null
      ? 'waiting…'
      : (() => {
          const seconds = Math.round(clock / 1000 - lastLlmAt)
          return seconds < 5 ? 'just now' : `${seconds}s ago`
        })()

  return (
    <div className="live-indicator">
      <PulseDot active={lit} color="#58b8ff" />
      <span className="live-indicator__label">llm</span>
      <span className="live-indicator__value" style={{ color: lit ? '#58b8ff' : '#d7e1ed' }}>
        {ago}
      </span>
    </div>
  )
}

function trainingTone(training: TrainingStatus): string {
  switch (training.status) {
    case 'disabled':
      return '#94a3b8'
    case 'running':
    case 'pending':
      return '#f59e0b'
    case 'completed':
      return '#22c55e'
    case 'failed':
      return '#ef4444'
    default:
      return '#94a3b8'
  }
}

function trainingLabel(training: TrainingStatus): string {
  switch (training.status) {
    case 'disabled':
      return 'OFF'
    case 'pending':
      return 'QUEUEING'
    case 'running':
      return training.total_count > 0 ? `${training.completed_count}/${training.total_count}` : 'RUNNING'
    case 'completed':
      return training.total_count > 0 ? `DONE ${training.completed_count}/${training.total_count}` : 'DONE'
    case 'failed':
      return 'FAILED'
    default:
      return 'ARMED'
  }
}

function trainingMeta(training: TrainingStatus): string {
  switch (training.status) {
    case 'disabled':
      return 'post-game training disabled'
    case 'pending':
      return 'post-game learner queued'
    case 'running':
      return training.current_agent_id
        ? `${training.current_agent_id}${training.current_behavior ? ` · ${training.current_behavior}` : ''}`
        : 'processing agents'
    case 'completed':
      return training.total_count > 0 ? `${training.completed_count} of ${training.total_count} agents learned` : 'learning finished'
    case 'failed':
      return training.error || 'learning pass failed'
    default:
      return 'ready for terminal run'
  }
}

function HeaderMetric({
  label,
  value,
  meta,
  tone,
  children,
}: {
  label: string
  value?: string
  meta?: string
  tone?: string
  children?: ReactNode
}) {
  return (
    <div className="header-metric">
      <div className="header-metric__label">{label}</div>
      {children ?? (
        <div className="header-metric__value" style={tone ? { color: tone } : undefined}>
          {value}
        </div>
      )}
      {meta && <div className="header-metric__meta">{meta}</div>}
    </div>
  )
}

export function CityHeader({ state, serverTick, lastLlmAt, onRestart, onStop, serverStopped = false }: Props) {
  const [busy, setBusy] = useState<'restart' | 'stop' | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)

  const handleRestart = async () => {
    if (busy) return
    setBusy('restart')
    setActionMsg('Restarting…')
    try {
      await restartServer()
      setActionMsg('Restarted.')
      onRestart?.()
    } catch (error) {
      setActionMsg(`Error: ${error}`)
    } finally {
      setBusy(null)
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  const handleStop = async () => {
    if (busy) return
    if (!window.confirm('Stop the server? The UI will disconnect.')) return
    setBusy('stop')
    setActionMsg('Stopping…')
    onStop?.()
    try {
      await stopServer()
      setActionMsg('Server stopped.')
    } catch {
      setActionMsg('Server stopped.')
    }
  }

  const elapsed = Math.max(0, state.now - state.started_at)
  const remaining = Math.max(0, state.season_seconds - elapsed)
  const elapsedMin = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const elapsedSec = Math.floor(elapsed % 60).toString().padStart(2, '0')
  const remMin = Math.floor(remaining / 60).toString().padStart(2, '0')
  const remSec = Math.floor(remaining % 60).toString().padStart(2, '0')

  const heatPct = Math.min(100, Math.max(0, state.heat))
  const heatColor = heatPct >= 70 ? '#ef4444' : heatPct >= 40 ? '#f59e0b' : '#22c55e'
  const heatBand = heatPct >= 70 ? 'critical' : heatPct >= 40 ? 'watch' : 'stable'
  const citizenList = Object.values(state.citizens)
  const jailedCount = citizenList.filter((citizen) => citizen.statuses.some((status) => status.effect === 'JAILED')).length
  const jammedCount = citizenList.filter((citizen) => citizen.statuses.some((status) => status.effect === 'JAMMED')).length
  const blockedCount = citizenList.filter((citizen) =>
    citizen.statuses.some((status) => status.effect === 'JAILED' || status.effect === 'JAMMED'),
  ).length
  const mayorEta = Math.max(0, state.mayor_next_tick_at - state.now)
  const jamRemaining = Math.max(0, state.server_scan_jammed_until - state.now)
  const training = state.training
  const trainingColor = trainingTone(training)
  const trainingActive = training.status === 'pending' || training.status === 'running'

  let statusLabel = 'RUNNING'
  let statusColor = '#58b8ff'

  if (serverStopped) {
    statusLabel = 'SERVER STOPPED'
    statusColor = '#94a3b8'
  } else if (state.is_finished) {
    statusLabel = state.winner === 'citizens' ? 'CITIZENS VICTORY' : 'MAYOR CONTROL'
    statusColor = state.winner === 'citizens' ? '#22c55e' : '#f87171'
  }

  return (
    <header className="city-header">
      <div className="city-header__grid">
        <div className="city-header__identity">
          <div className="city-header__eyebrow">OptimiCity</div>
          <h1 className="city-header__title">Simulation control room</h1>
          <div className="city-header__runline">
            <span className="city-header__runid" title={state.game_id}>
              run {state.game_id.slice(0, 8)}
            </span>
            <span
              className="city-header__status"
              style={{ color: statusColor, borderColor: hexToRgba(statusColor, 0.28) }}
            >
              {statusLabel}
            </span>
            {(state.is_finished || training.status === 'failed') && (
              <span
                className="city-header__status"
                style={{ color: trainingColor, borderColor: hexToRgba(trainingColor, 0.28) }}
              >
                TRAINING {trainingLabel(training)}
              </span>
            )}
          </div>
        </div>

        <div className="city-header__heat">
          <div className="city-header__heat-topline">
            <span className="city-header__heat-label">City heat</span>
            <span className="city-header__heat-value" style={{ color: heatColor }}>
              {state.heat.toFixed(1)} / 100
            </span>
          </div>
          <div className="city-header__heat-band">
            <span>{heatBand}</span>
            <span>hour {(state.game_hour ?? 0).toFixed(1)} / 72</span>
          </div>
          <div className="city-header__heat-track">
            <div
              className="city-header__heat-fill"
              style={{
                width: `${heatPct}%`,
                background: `linear-gradient(90deg, ${hexToRgba(heatColor, 0.65)} 0%, ${heatColor} 100%)`,
              }}
            />
          </div>
          <div className="city-header__heat-footline">
            <span>{elapsedMin}:{elapsedSec} elapsed</span>
            <span>{remMin}:{remSec} left</span>
          </div>
        </div>

        <div className="city-header__telemetry">
          <HeaderMetric label="Loop activity" meta="server tick">
            <TickIndicator label="server" tick={serverTick} color="#4cd2b7" />
          </HeaderMetric>
          <HeaderMetric label="Model activity" meta="last language-model event">
            <LlmIndicator lastLlmAt={lastLlmAt} />
          </HeaderMetric>
          <HeaderMetric
            label="Citizen pressure"
            value={`${blockedCount} blocked`}
            meta={`${jailedCount} jailed · ${jammedCount} jammed`}
            tone={blockedCount > 0 ? '#ffb457' : '#d7e1ed'}
          />
          <HeaderMetric
            label={state.is_finished ? 'Training' : 'Mayor next'}
            meta={state.is_finished ? trainingMeta(training) : jamRemaining > 0 ? `scan jam ${jamRemaining.toFixed(0)}s` : 'scan net clear'}
          >
            {state.is_finished ? (
              <div className="live-indicator">
                <PulseDot active={trainingActive} color={trainingColor} />
                <span className="live-indicator__label">training</span>
                <span className="live-indicator__value" style={{ color: trainingColor }}>
                  {trainingLabel(training)}
                </span>
              </div>
            ) : (
              <div className="header-metric__value" style={jamRemaining > 0 ? { color: '#ffb457' } : undefined}>
                {mayorEta.toFixed(0)}s
              </div>
            )}
          </HeaderMetric>
        </div>

        <div className="city-header__controls">
          <div className="city-header__buttons">
            <button onClick={handleRestart} disabled={busy !== null} className="button button--primary">
              {busy === 'restart' ? 'Restarting…' : 'Restart runtime'}
            </button>
            <button onClick={handleStop} disabled={busy !== null} className="button button--danger">
              {busy === 'stop' ? 'Stopping…' : 'Stop server'}
            </button>
          </div>
          {actionMsg && <span className="city-header__action-msg">{actionMsg}</span>}
        </div>
      </div>
    </header>
  )
}
