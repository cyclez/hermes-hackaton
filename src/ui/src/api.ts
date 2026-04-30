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

export interface DecisionLogAttempt {
  attempt: number
  repair: boolean
  ok: boolean
  prompt: string
  response: string
  validation_error: string | null
  usage: Record<string, number>
  api_calls: number | null
  elapsed_seconds: number | null
}

export interface DecisionLogEntry {
  log_id: string
  game_id: string
  ts: number
  role: string
  agent_id: string
  behavior: string
  model: string
  summary: string
  situation: Record<string, unknown>
  attempts: DecisionLogAttempt[]
  final: {
    ok: boolean
    payload: Record<string, unknown>
  }
}

export interface DecisionLogRun {
  game_id: string
  updated_at: number | null
  entry_count: number
}

export async function fetchDecisionLogRuns(): Promise<{ current_game_id: string, runs: DecisionLogRun[] }> {
  const r = await fetch('/api/decision-log-runs')
  if (!r.ok) throw new Error(`decision log runs ${r.status}`)
  return r.json()
}

export async function fetchDecisionLogs(params: {
  gameId?: string
  limit?: number
  role?: string
  agentId?: string
} = {}): Promise<DecisionLogEntry[]> {
  const query = new URLSearchParams({ limit: String(params.limit ?? 200) })
  if (params.gameId) query.set('game_id', params.gameId)
  if (params.role) query.set('role', params.role)
  if (params.agentId) query.set('agent_id', params.agentId)
  const r = await fetch(`/api/decision-logs?${query}`)
  if (!r.ok) throw new Error(`decision logs ${r.status}`)
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
