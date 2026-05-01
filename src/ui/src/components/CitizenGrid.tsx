import type { CityState } from '../api'
import { CitizenCard } from './CitizenCard'

interface Props {
  state: CityState
}

export function CitizenGrid({ state }: Props) {
  const citizens = Object.values(state.citizens).sort((a, b) => a.citizen_id.localeCompare(b.citizen_id))
  const blockedCount = citizens.filter((citizen) =>
    citizen.statuses.some((status) => status.effect === 'JAILED' || status.effect === 'JAMMED'),
  ).length
  const queuedCount = citizens.filter((citizen) => citizen.queued_mode !== null).length
  const avgTrace =
    citizens.length > 0
      ? citizens.reduce((sum, citizen) => sum + citizen.trace, 0) / citizens.length
      : 0

  return (
    <section className="panel citizen-section">
      <div className="citizen-section__header">
        <div>
          <div className="panel-kicker">Citizen network</div>
          <h2 className="panel-title">Citizens</h2>
        </div>

        <div className="citizen-strip">
          <div className="citizen-strip__metric">
            <span className="citizen-strip__value">{citizens.length}</span>
            <span className="citizen-strip__label">citizens</span>
          </div>
          <div className="citizen-strip__metric">
            <span className="citizen-strip__value">{blockedCount}</span>
            <span className="citizen-strip__label">blocked</span>
          </div>
          <div className="citizen-strip__metric">
            <span className="citizen-strip__value">{queuedCount}</span>
            <span className="citizen-strip__label">queued</span>
          </div>
          <div className="citizen-strip__metric">
            <span className="citizen-strip__value">{avgTrace.toFixed(1)}</span>
            <span className="citizen-strip__label">avg trace</span>
          </div>
        </div>
      </div>

      <div className="citizen-grid">
        {citizens.map((citizen) => (
          <CitizenCard key={citizen.citizen_id} citizen={citizen} now={state.now} />
        ))}
      </div>
    </section>
  )
}
