import type { CityState } from '../api'
import { CitizenCard } from './CitizenCard'

interface Props {
  state: CityState
}

export function CitizenGrid({ state }: Props) {
  const citizens = Object.values(state.citizens).sort((a, b) => a.citizen_id.localeCompare(b.citizen_id))

  return (
    <div>
      <h2 style={{ color: '#94a3b8', fontSize: 13, fontWeight: 600, margin: '0 0 12px', textTransform: 'uppercase', letterSpacing: 1 }}>
        Citizens ({citizens.length})
      </h2>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        gap: 12,
      }}>
        {citizens.map(c => (
          <CitizenCard key={c.citizen_id} citizen={c} now={state.now} />
        ))}
      </div>
    </div>
  )
}
