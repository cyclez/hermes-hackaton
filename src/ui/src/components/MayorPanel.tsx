import type { CSSProperties } from 'react'
import type { MayorDecree } from '../api'
import { formatClockTime, formatTokenLabel, hexToRgba } from '../ui'

interface Props {
  decree: MayorDecree | null
}

const ACTION_COLORS: Record<string, string> = {
  SURVEIL: '#ff9f5c',
  ARREST: '#ff6c67',
  JAM_SERVER: '#f2c66c',
  BRIBE: '#b0a0ff',
  RELEASE: '#7fd8a8',
  PARDON: '#7fd8a8',
}

export function MayorPanel({ decree }: Props) {
  const accent = ACTION_COLORS[decree?.action ?? ''] ?? '#ffb457'
  const panelStyle = {
    ['--mayor-accent' as string]: accent,
  } as CSSProperties

  return (
    <section className="panel mayor-panel" style={panelStyle}>
      <div className="panel-kicker">Mayor desk</div>
      <div className="mayor-panel__header">
        <div>
          <h2 className="panel-title">Latest decree</h2>
          <p className="panel-copy">Authority actions and rationale appear here as the simulation updates.</p>
        </div>
        <span
          className="chip"
          style={{
            color: accent,
            background: hexToRgba(accent, 0.12),
            borderColor: hexToRgba(accent, 0.34),
          }}
        >
          mayor
        </span>
      </div>

      {!decree ? (
        <div className="mayor-panel__empty">
          No decrees yet. When the Mayor acts, the active order, targets, and justification will be pinned here.
        </div>
      ) : (
        <>
          <div className="mayor-panel__hero">
            <span
              className="mayor-panel__action"
              style={{
                color: accent,
                background: hexToRgba(accent, 0.14),
                borderColor: hexToRgba(accent, 0.34),
              }}
            >
              {formatTokenLabel(decree.action)}
            </span>
            <div className="mayor-panel__hero-meta">
              <span>{decree.targets.length} target{decree.targets.length === 1 ? '' : 's'}</span>
              <span>{decree.duration_seconds > 0 ? `${decree.duration_seconds}s window` : 'instant effect'}</span>
              <span>{formatClockTime(decree.created_at)}</span>
            </div>
          </div>

          <div className="mayor-panel__targets">
            {decree.targets.map((target) => (
              <span key={target} className="chip chip--neutral">
                {target}
              </span>
            ))}
          </div>

          <div className="mayor-panel__rationale">{decree.rationale}</div>
        </>
      )}
    </section>
  )
}
