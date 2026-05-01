import { useEffect, useEffectEvent, useState } from 'react'
import type { AgentTurn, CityState, GameEvent, MayorDecree } from './api'
import { fetchAgentLogs, fetchEvents, fetchMayorDecree, fetchState } from './api'
import { ActivityPanel } from './components/ActivityPanel'
import { AgentConsoles } from './components/AgentConsoles'
import { DecisionLogPage } from './components/DecisionLogPage'
import { CityHeader } from './components/CityHeader'
import { CitizenGrid } from './components/CitizenGrid'
import { MayorPanel } from './components/MayorPanel'

const CITIZEN_KINDS = ['citizen_action', 'mode_change', 'citizen_jailed', 'citizen_released']
const MAYOR_KINDS = ['mayor_decree', 'invalid_decision']
const SYSTEM_KINDS = ['heat_change', 'game_start', 'game_end']
const TICK_KINDS = ['server_tick']

function usePathname() {
  const [pathname, setPathname] = useState(window.location.pathname)

  useEffect(() => {
    const onPop = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  return pathname
}

function HomePage() {
  const [state, setState] = useState<CityState | null>(null)
  const [citizenEvents, setCitizenEvents] = useState<GameEvent[]>([])
  const [mayorEvents, setMayorEvents] = useState<GameEvent[]>([])
  const [systemEvents, setSystemEvents] = useState<GameEvent[]>([])
  const [decree, setDecree] = useState<MayorDecree | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [serverTick, setServerTick] = useState(0)
  const [lastLlmAt, setLastLlmAt] = useState<number | null>(null)
  const [agentLogs, setAgentLogs] = useState<Record<string, AgentTurn[]>>({})
  const [serverStopped, setServerStopped] = useState(false)
  const [refreshNonce, setRefreshNonce] = useState(0)

  const poll = useEffectEvent(async () => {
    if (serverStopped) return
    try {
      const running = !state?.is_finished
      const [s, ce, me, se, tickEvents, d, al] = await Promise.all([
        fetchState(),
        running ? fetchEvents(24, CITIZEN_KINDS) : Promise.resolve(citizenEvents),
        running ? fetchEvents(12, MAYOR_KINDS) : Promise.resolve(mayorEvents),
        fetchEvents(12, SYSTEM_KINDS),
        fetchEvents(1, TICK_KINDS),
        running ? fetchMayorDecree() : Promise.resolve(decree),
        running ? fetchAgentLogs() : Promise.resolve(agentLogs),
      ])
      setState(s)
      setCitizenEvents(ce)
      setMayorEvents(me)
      setSystemEvents(se)
      setDecree(d)
      setAgentLogs(al)
      setError(null)

      const latestTick = tickEvents[0]
      if (latestTick) setServerTick(latestTick.tick)

      const latestLlm = ce.find((event) => event.kind === 'citizen_action') ?? me.find((event) => event.kind === 'mayor_decree')
      if (latestLlm) setLastLlmAt(Date.now() / 1000)
    } catch (err) {
      setError(String(err))
    }
  })

  useEffect(() => {
    if (serverStopped) return
    let cancelled = false
    let timeoutId: number | null = null
    const trainingActive = state?.training?.status === 'pending' || state?.training?.status === 'running'

    const schedule = (delayMs: number) => {
      timeoutId = window.setTimeout(async () => {
        await poll()
        if (cancelled) return
        schedule(!state?.is_finished ? 2000 : trainingActive ? 3000 : 15000)
      }, delayMs)
    }

    schedule(0)

    return () => {
      cancelled = true
      if (timeoutId !== null) window.clearTimeout(timeoutId)
    }
  }, [refreshNonce, serverStopped, state?.is_finished, state?.training?.status])

  if (error && !state) {
    return (
      <div className="app-status-screen">
        <div className="panel panel--status">
          <div className="app-status-screen__kicker">Connection error</div>
          <strong className="app-status-screen__title">{error}</strong>
          <div className="app-status-screen__hint">
            Is the server running? <code>uvicorn src.server.app:app --reload</code>
          </div>
        </div>
      </div>
    )
  }

  if (!state) {
    return (
      <div className="app-status-screen">
        <div className="panel panel--status">
          <div className="app-status-screen__kicker">Simulation console</div>
          <strong className="app-status-screen__title">Connecting to runtime…</strong>
          <div className="app-status-screen__hint">Waiting for the existing backend and event stream.</div>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <CityHeader
        state={state}
        serverTick={serverTick}
        lastLlmAt={lastLlmAt}
        onRestart={() => {
          setServerStopped(false)
          setAgentLogs({})
          setCitizenEvents([])
          setMayorEvents([])
          setSystemEvents([])
          setDecree(null)
          setLastLlmAt(null)
          setRefreshNonce((value) => value + 1)
        }}
        onStop={() => setServerStopped(true)}
        serverStopped={serverStopped}
      />

      <main className="app-main">
        {error && (
          <div className="panel panel--alert">
            <div className="panel-kicker">Polling degraded</div>
            <div className="panel-copy">{error}</div>
          </div>
        )}

        <section className="app-primary">
          <CitizenGrid state={state} />
        </section>

        <aside className="app-sidebar">
          <ActivityPanel
            citizenEvents={citizenEvents}
            mayorEvents={mayorEvents}
            systemEvents={systemEvents}
          />

          <MayorPanel decree={decree} />
        </aside>

        <AgentConsoles logs={agentLogs} />
      </main>
    </div>
  )
}

export default function App() {
  const pathname = usePathname()

  if (pathname === '/decision-logs') {
    return <DecisionLogPage />
  }

  return <HomePage />
}
