import { useEffect, useRef, useState } from 'react'
import type { CityState } from '../api'
import { restartServer, stopServer } from '../api'

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
    <span style={{
      display: 'inline-block',
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: color,
      opacity: active ? 1 : 0.25,
      transition: 'opacity 0.15s',
      flexShrink: 0,
    }} />
  )
}

function TickIndicator({ label, tick, color }: { label: string; tick: number; color: string }) {
  const [lit, setLit] = useState(false)
  const prev = useRef(tick)

  useEffect(() => {
    if (tick !== prev.current) {
      prev.current = tick
      setLit(true)
      const t = setTimeout(() => setLit(false), 300)
      return () => clearTimeout(t)
    }
  }, [tick])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <PulseDot active={lit} color={color} />
      <span style={{ color: '#64748b', fontSize: 11 }}>{label}</span>
      <span style={{ color: lit ? color : '#94a3b8', fontSize: 11, fontVariantNumeric: 'tabular-nums', transition: 'color 0.15s' }}>
        {tick}
      </span>
    </div>
  )
}

function LlmIndicator({ lastLlmAt }: { lastLlmAt: number | null }) {
  const [lit, setLit] = useState(false)
  const prev = useRef(lastLlmAt)
  const [ago, setAgo] = useState<string>('waiting…')

  useEffect(() => {
    if (lastLlmAt !== null && lastLlmAt !== prev.current) {
      prev.current = lastLlmAt
      setLit(true)
      const t = setTimeout(() => setLit(false), 800)
      return () => clearTimeout(t)
    }
  }, [lastLlmAt])

  useEffect(() => {
    if (lastLlmAt === null) { setAgo('waiting…'); return }
    const update = () => {
      const s = Math.round((Date.now() / 1000) - lastLlmAt)
      setAgo(s < 5 ? 'just now' : `${s}s ago`)
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [lastLlmAt])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <PulseDot active={lit} color="#60a5fa" />
      <span style={{ color: '#64748b', fontSize: 11 }}>LLM</span>
      <span style={{ color: lit ? '#60a5fa' : '#94a3b8', fontSize: 11, transition: 'color 0.15s' }}>
        {ago}
      </span>
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
      setActionMsg('Restarted ✓')
      onRestart?.()
    } catch (e) {
      setActionMsg(`Error: ${e}`)
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
    } catch (e) {
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

  let statusLabel = 'RUNNING'
  let statusColor = '#60a5fa'
  if (serverStopped) {
    statusLabel = 'SERVER STOPPED'
    statusColor = '#94a3b8'
  } else if (state.is_finished) {
    statusLabel = state.winner === 'citizens' ? '🏆 CITIZENS WIN' : '🏛 MAYOR WINS'
    statusColor = state.winner === 'citizens' ? '#22c55e' : '#f87171'
  }

  return (
    <div style={{ padding: '14px 24px', background: '#1e1e2e', borderBottom: '1px solid #333' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <h1 style={{ margin: 0, fontSize: 18, color: '#e2e8f0', whiteSpace: 'nowrap' }}>OptimiCity</h1>

        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ color: '#94a3b8', fontSize: 13 }}>
              Heat: <strong style={{ color: heatColor }}>{state.heat.toFixed(1)}</strong> / 100
            </span>
            <span style={{ color: '#94a3b8', fontSize: 13 }}>
              Hour: <strong style={{ color: '#e2e8f0' }}>{(state.game_hour ?? 0).toFixed(1)}</strong> / 72
            </span>
          </div>
          <div style={{ background: '#374151', borderRadius: 4, height: 8, overflow: 'hidden' }}>
            <div style={{ width: `${heatPct}%`, height: '100%', background: heatColor, transition: 'width 0.5s' }} />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 120 }}>
          <TickIndicator label="server" tick={serverTick} color="#22c55e" />
          <LlmIndicator lastLlmAt={lastLlmAt} />
        </div>

        <div style={{ textAlign: 'right', minWidth: 150 }}>
          <div style={{ color: statusColor, fontWeight: 700, fontSize: 13 }}>{statusLabel}</div>
          <div style={{ color: '#64748b', fontSize: 11 }}>
            {elapsedMin}:{elapsedSec} elapsed · {remMin}:{remSec} left
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleRestart}
              disabled={busy !== null}
              style={{
                background: busy === 'restart' ? '#1e3a8a' : '#1d4ed8',
                color: busy !== null ? '#93c5fd' : '#fff',
                border: 'none',
                borderRadius: 5,
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: busy !== null ? 'not-allowed' : 'pointer',
                opacity: busy !== null && busy !== 'restart' ? 0.4 : 1,
              }}
            >{busy === 'restart' ? '↺ …' : '↺ Restart'}</button>
            <button
              onClick={handleStop}
              disabled={busy !== null}
              style={{
                background: '#7f1d1d',
                color: busy !== null ? '#fca5a5' : '#fca5a5',
                border: 'none',
                borderRadius: 5,
                padding: '5px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: busy !== null ? 'not-allowed' : 'pointer',
                opacity: busy !== null && busy !== 'stop' ? 0.4 : 1,
              }}
            >{busy === 'stop' ? '■ …' : '■ Stop'}</button>
          </div>
          {actionMsg && (
            <span style={{ fontSize: 10, color: '#94a3b8' }}>{actionMsg}</span>
          )}
        </div>
      </div>
    </div>
  )
}
