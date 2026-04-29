export interface TimedStatus {
  effect: string
  expires_at: number
}

export interface Citizen {
  citizen_id: string
  behavior: string
  mode: string
  queued_mode: string | null
  stk: number
  shiva: number
  trace: number
  last_decision_at: number
  action_cooldown_until: number
  statuses: TimedStatus[]
}

export interface CityState {
  game_id: string
  season_seconds: number
  started_at: number
  now: number
  heat: number
  server_scan_jammed_until: number
  mayor_next_tick_at: number
  citizens: Record<string, Citizen>
  game_hour: number
  is_finished: boolean
  winner: string | null
}

export interface GameEvent {
  event_id: string
  tick: number
  game_hour: number
  kind: string
  message: string
  payload: Record<string, unknown>
  public: boolean
}

export interface MayorDecree {
  action: string
  targets: string[]
  rationale: string
  duration_seconds: number
  created_at: string | null
}

export async function fetchState(): Promise<CityState> {
  const r = await fetch('/api/state')
  if (!r.ok) throw new Error(`state ${r.status}`)
  return r.json()
}

export async function fetchEvents(limit = 30, kinds?: string[]): Promise<GameEvent[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (kinds && kinds.length > 0) params.set('kinds', kinds.join(','))
  const r = await fetch(`/api/events?${params}`)
  if (!r.ok) throw new Error(`events ${r.status}`)
  return r.json()
}

export interface AgentTurn {
  ts: number
  agent_id: string
  prompt: string
  response: string
  decision: string
  ok: boolean
  repair: boolean
}

export async function fetchAgentLogs(): Promise<Record<string, AgentTurn[]>> {
  const r = await fetch('/api/agents/logs')
  if (!r.ok) throw new Error(`agent logs ${r.status}`)
  return r.json()
}

export async function stopServer(): Promise<void> {
  await fetch('/api/server/stop', { method: 'POST' })
}

export async function restartServer(): Promise<void> {
  await fetch('/api/server/restart', { method: 'POST' })
}

export async function fetchMayorDecree(): Promise<MayorDecree | null> {
  const r = await fetch('/api/mayor/latest')
  if (!r.ok) throw new Error(`mayor ${r.status}`)
  const data = await r.json()
  return Object.keys(data).length === 0 ? null : data
}
