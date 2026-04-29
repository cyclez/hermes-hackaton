import { useEffect, useState } from 'react'
import type { AgentTurn, CityState, GameEvent, MayorDecree } from './api'
import { fetchAgentLogs, fetchEvents, fetchMayorDecree, fetchState } from './api'
import { AgentConsoles } from './components/AgentConsoles'
import { CityHeader } from './components/CityHeader'
import { CitizenGrid } from './components/CitizenGrid'
import { Feed } from './components/Feed'
import { MayorPanel } from './components/MayorPanel'

const CITIZEN_KINDS = ['citizen_action', 'mode_change', 'citizen_jailed', 'citizen_released']
const MAYOR_KINDS   = ['mayor_decree', 'invalid_decision']
const SYSTEM_KINDS  = ['server_tick', 'heat_change', 'game_start', 'game_end']

export default function App() {
  const [state, setState] = useState<CityState | null>(null)
  const [citizenEvents, setCitizenEvents] = useState<GameEvent[]>([])
  const [mayorEvents, setMayorEvents] = useState<GameEvent[]>([])
  const [systemEvents, setSystemEvents] = useState<GameEvent[]>([])
  const [decree, setDecree] = useState<MayorDecree | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [serverTick, setServerTick] = useState(0)
  const [lastLlmAt, setLastLlmAt] = useState<number | null>(null)
  const [agentLogs, setAgentLogs] = useState<Record<string, AgentTurn[]>>({})

  const poll = async () => {
    try {
      const [s, ce, me, se, d, al] = await Promise.all([
        fetchState(),
        fetchEvents(40, CITIZEN_KINDS),
        fetchEvents(20, MAYOR_KINDS),
        fetchEvents(20, SYSTEM_KINDS),
        fetchMayorDecree(),
        fetchAgentLogs(),
      ])
      setState(s)
      setCitizenEvents(ce)
      setMayorEvents(me)
      setSystemEvents(se)
      setDecree(d)
      setAgentLogs(al)
      setError(null)

      const latestTick = se.find(ev => ev.kind === 'server_tick')
      if (latestTick) setServerTick(latestTick.tick)

      const latestLlm = ce.find(ev => ev.kind === 'citizen_action') ?? me.find(ev => ev.kind === 'mayor_decree')
      if (latestLlm) setLastLlmAt(Date.now() / 1000)
    } catch (err) {
      setError(String(err))
    }
  }

  useEffect(() => {
    poll()
    const id = setInterval(poll, 2000)
    return () => clearInterval(id)
  }, [])

  if (error && !state) {
    return (
      <div style={{ padding: 32, color: '#f87171', fontFamily: 'monospace' }}>
        <strong>Connection error:</strong> {error}
        <div style={{ color: '#64748b', marginTop: 8, fontSize: 13 }}>
          Is the server running? <code>uvicorn src.server.app:app --reload</code>
        </div>
      </div>
    )
  }

  if (!state) {
    return <div style={{ padding: 32, color: '#64748b' }}>Connecting…</div>
  }

  return (
    // Full viewport, column flex so header + content fill exactly 100vh
    <div style={{
      height: '100vh',
      display: 'flex',
      flexDirection: 'column',
      background: '#0f172a',
      fontFamily: 'system-ui, sans-serif',
      overflow: 'hidden',
    }}>
      <CityHeader
        state={state}
        serverTick={serverTick}
        lastLlmAt={lastLlmAt}
        onRestart={() => {
          // Immediately wipe stale state so the UI shows fresh data
          setAgentLogs({})
          setCitizenEvents([])
          setMayorEvents([])
          setSystemEvents([])
          setDecree(null)
          setLastLlmAt(null)
          poll()
        }}
      />

      {/* Content row: fills remaining height, no overflow at this level */}
      <div style={{
        flex: 1,
        display: 'flex',
        gap: 20,
        padding: '16px 24px',
        minHeight: 0,           // critical: lets flex children shrink below content size
        overflow: 'hidden',
      }}>

        {/* LEFT — citizens + agent consoles, scrollable */}
        <div style={{ flex: 1, overflowY: 'auto', minWidth: 0 }}>
          <CitizenGrid state={state} />
          <AgentConsoles logs={agentLogs} />
        </div>

        {/* RIGHT — fixed-height logs panel, never expands */}
        <div style={{
          width: 380,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          overflow: 'hidden',   // right panel is sealed — feeds scroll inside themselves
        }}>
          <MayorPanel decree={decree} />

          {/* Three feeds share whatever height remains after MayorPanel */}
          <Feed label="Citizen Actions" events={citizenEvents} accent="#60a5fa" />
          <Feed label="Mayor / LLM"     events={mayorEvents}   accent="#fb923c" />
          <Feed label="System Events"   events={systemEvents}  accent="#475569" />
        </div>
      </div>
    </div>
  )
}
