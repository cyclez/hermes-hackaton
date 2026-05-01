import type { CSSProperties } from 'react'
import type { Citizen } from '../api'
import { formatBehaviorLabel, hexToRgba } from '../ui'

const MODE_COLORS: Record<string, string> = {
  MINE: '#58b8ff',
  SYNC: '#4cd2b7',
  SLEEP: '#93a2b7',
}

const STATUS_COLORS: Record<string, string> = {
  JAILED: '#ff6c67',
  SURVEILLED: '#ff9f5c',
  JAMMED: '#f2c66c',
  GHOSTED: '#7de2ff',
  PROTECTED: '#7fd8a8',
}

function ResourceCard({
  label,
  value,
  max,
  color,
  digits = 0,
}: {
  label: string
  value: number
  max: number
  color: string
  digits?: number
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))

  return (
    <div className="resource-card">
      <div className="resource-card__head">
        <span className="resource-card__label">{label}</span>
        <span className="resource-card__value">{value.toFixed(digits)}</span>
      </div>
      <div className="resource-card__track">
        <div
          className="resource-card__fill"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${hexToRgba(color, 0.6)} 0%, ${color} 100%)`,
          }}
        />
      </div>
    </div>
  )
}

interface Props {
  citizen: Citizen
  now: number
}

export function CitizenCard({ citizen, now }: Props) {
  const statuses = citizen.statuses.map((status) => status.effect)
  const modeColor = MODE_COLORS[citizen.mode] ?? '#93a2b7'
  const cooldownLeft = Math.max(0, citizen.action_cooldown_until - now)
  const decisionAge = Math.max(0, now - citizen.last_decision_at)
  const isJailed = statuses.includes('JAILED')
  const isJammed = statuses.includes('JAMMED')
  const isSurveilled = statuses.includes('SURVEILLED')

  let readinessLabel = 'Action-ready'
  if (isJailed) readinessLabel = 'Execution frozen'
  else if (isJammed) readinessLabel = 'Actions jammed'
  else if (cooldownLeft > 0) readinessLabel = `${cooldownLeft.toFixed(0)}s cooldown`

  let riskLabel = 'Stable'
  let riskColor = '#4cd2b7'
  if (isJailed) {
    riskLabel = 'Lockdown'
    riskColor = '#ff6c67'
  } else if (citizen.trace >= 65 || isSurveilled) {
    riskLabel = 'High trace'
    riskColor = '#ff9f5c'
  } else if (citizen.trace >= 35 || isJammed) {
    riskLabel = 'Watchlist'
    riskColor = '#f2c66c'
  }

  const cardStyle = {
    ['--citizen-accent' as string]: modeColor,
    ['--citizen-risk' as string]: riskColor,
  } as CSSProperties

  return (
    <article className="citizen-card" style={cardStyle}>
      <div className="citizen-card__top">
        <div className="citizen-card__identity">
          <div className="citizen-card__id">{citizen.citizen_id}</div>
          <div className="citizen-card__behavior">{formatBehaviorLabel(citizen.behavior)}</div>
        </div>

        <div className="citizen-card__badges">
          <span
            className="chip"
            style={{
              color: modeColor,
              background: hexToRgba(modeColor, 0.14),
              borderColor: hexToRgba(modeColor, 0.36),
            }}
          >
            {citizen.mode}
          </span>
          <span
            className="chip"
            style={{
              color: riskColor,
              background: hexToRgba(riskColor, 0.14),
              borderColor: hexToRgba(riskColor, 0.34),
            }}
          >
            {riskLabel}
          </span>
        </div>
      </div>

      <div className="citizen-card__meta">
        <span>{readinessLabel}</span>
        <span>last decision {decisionAge.toFixed(0)}s ago</span>
        <span>{citizen.queued_mode ? `queued ${citizen.queued_mode}` : 'no queued mode'}</span>
      </div>

      {statuses.length > 0 && (
        <div className="citizen-card__status-row">
          {statuses.map((status) => {
            const color = STATUS_COLORS[status] ?? '#8ea3bb'
            return (
              <span
                key={status}
                className="chip"
                style={{
                  color,
                  background: hexToRgba(color, 0.14),
                  borderColor: hexToRgba(color, 0.34),
                }}
              >
                {status}
              </span>
            )
          })}
        </div>
      )}

      <div className="citizen-card__resources">
        <ResourceCard
          label="STK"
          value={citizen.stk}
          max={3000}
          color="#8a9dff"
        />
        <ResourceCard
          label="SHIVA"
          value={citizen.shiva}
          max={100}
          color="#4cd2b7"
          digits={1}
        />
        <ResourceCard
          label="TRACE"
          value={citizen.trace}
          max={100}
          color={riskColor}
          digits={1}
        />
      </div>
    </article>
  )
}
