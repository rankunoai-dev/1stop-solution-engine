import type { SpendRow } from '../api/types'

interface Props {
  rows: SpendRow[]
}

const VIEW_W = 560
const VIEW_H = 180
const PAD_L = 48
const PAD_R = 16
const PAD_T = 16
const PAD_B = 32
const PLOT_W = VIEW_W - PAD_L - PAD_R
const PLOT_H = VIEW_H - PAD_T - PAD_B

function fmtDay(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function fmtUsd(v: number): string {
  return `$${v.toFixed(4)}`
}

// Aggregate rows by day (sum cost_usd across purposes)
function aggregateByDay(rows: SpendRow[]): { day: string; cost: number }[] {
  const map = new Map<string, number>()
  for (const r of rows) {
    map.set(r.day, (map.get(r.day) ?? 0) + r.cost_usd)
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, cost]) => ({ day, cost }))
}

export function SpendChart({ rows }: Props) {
  const data = aggregateByDay(rows)

  if (data.length === 0) {
    return (
      <div className="spend-chart spend-chart--empty">
        <span>No spend data for this period.</span>
      </div>
    )
  }

  const maxCost = Math.max(...data.map((d) => d.cost), 0.0001)
  const barW = PLOT_W / data.length - 4

  return (
    <div className="spend-chart">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        aria-label="Daily spend bar chart"
        role="img"
        style={{ width: '100%', height: 'auto' }}
      >
        {/* Y-axis labels */}
        {[0, 0.5, 1].map((frac) => {
          const y = PAD_T + PLOT_H - frac * PLOT_H
          const val = frac * maxCost
          return (
            <g key={frac}>
              <line
                x1={PAD_L}
                y1={y}
                x2={VIEW_W - PAD_R}
                y2={y}
                stroke="var(--color-border)"
                strokeDasharray="4 2"
              />
              <text
                x={PAD_L - 4}
                y={y + 4}
                textAnchor="end"
                fontSize={10}
                fill="var(--color-text-muted)"
              >
                {fmtUsd(val)}
              </text>
            </g>
          )
        })}

        {/* Bars */}
        {data.map((d, i) => {
          const barH = (d.cost / maxCost) * PLOT_H
          const x = PAD_L + (PLOT_W / data.length) * i + 2
          const y = PAD_T + PLOT_H - barH

          return (
            <g key={d.day}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={barH}
                fill="var(--color-accent)"
                rx={2}
              />
              <text
                x={x + barW / 2}
                y={PAD_T + PLOT_H + 18}
                textAnchor="middle"
                fontSize={10}
                fill="var(--color-text-muted)"
              >
                {fmtDay(d.day)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
