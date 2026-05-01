export function formatTokenLabel(value: string): string {
  return value.replace(/_/g, ' ')
}

export function formatBehaviorLabel(value: string): string {
  return value.replace(/_/g, ' ')
}

export function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '')
  const fullHex =
    normalized.length === 3
      ? normalized
          .split('')
          .map((char) => char + char)
          .join('')
      : normalized

  const safeHex = fullHex.padEnd(6, '0').slice(0, 6)
  const red = Number.parseInt(safeHex.slice(0, 2), 16)
  const green = Number.parseInt(safeHex.slice(2, 4), 16)
  const blue = Number.parseInt(safeHex.slice(4, 6), 16)

  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

export function formatDateTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return 'n/a'

  const date =
    typeof value === 'number'
      ? new Date(value < 1_000_000_000_000 ? value * 1000 : value)
      : new Date(value)

  return Number.isNaN(date.getTime()) ? 'n/a' : date.toLocaleString()
}

export function formatClockTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return 'n/a'

  const date =
    typeof value === 'number'
      ? new Date(value < 1_000_000_000_000 ? value * 1000 : value)
      : new Date(value)

  return Number.isNaN(date.getTime())
    ? 'n/a'
    : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
