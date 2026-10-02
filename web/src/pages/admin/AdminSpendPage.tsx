import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NavBar } from '../../components/NavBar'
import { SpendChart } from '../../components/SpendChart'
import { api } from '../../api/client'
import type { SpendResponse } from '../../api/types'

function fmtUsd(v: number): string {
  return `$${v.toFixed(4)}`
}

export function AdminSpendPage() {
  const location = useLocation()
  const [data, setData] = useState<SpendResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    void load()
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.adminSpend(7)
      setData(resp)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load spend data')
    } finally {
      setLoading(false)
    }
  }

  async function handleToggleKillSwitch() {
    if (data === null) return
    setToggling(true)
    try {
      await api.setKillSwitch(!data.guard_status.kill_switch)
      await load()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to toggle kill switch')
    } finally {
      setToggling(false)
    }
  }

  const gs = data?.guard_status

  return (
    <div className="page-shell">
      <NavBar />
      <div className="admin-page">
        <div className="admin-page__header">
          <h1 className="admin-page__title">Admin</h1>
        </div>
        <nav className="admin-nav">
          <Link
            to="/admin/users"
            className={`admin-nav__link${location.pathname === '/admin/users' ? ' active' : ''}`}
          >
            Users
          </Link>
          <Link
            to="/admin/spend"
            className={`admin-nav__link${location.pathname === '/admin/spend' ? ' active' : ''}`}
          >
            Spend
          </Link>
          <Link
            to="/admin/jobs"
            className={`admin-nav__link${location.pathname === '/admin/jobs' ? ' active' : ''}`}
          >
            Jobs
          </Link>
        </nav>

        {loading && <p style={{ color: 'var(--color-text-muted)' }}>Loading…</p>}
        {error !== null && <p className="form-error">{error}</p>}

        {!loading && data !== null && (
          <>
            {gs !== undefined && (
              <div className={`kill-switch${gs.kill_switch ? ' kill-switch--active' : ''}`}>
                <div>
                  <div className="kill-switch__label">
                    Kill switch {gs.kill_switch ? '— ENABLED (all LLM calls blocked)' : '— disabled'}
                  </div>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-muted)' }}>
                    Blocks all LLM calls immediately when enabled.
                  </div>
                </div>
                <button
                  type="button"
                  className={`btn btn--sm ${gs.kill_switch ? 'btn--secondary' : 'btn--danger'}`}
                  onClick={() => { void handleToggleKillSwitch() }}
                  disabled={toggling}
                >
                  {toggling ? 'Updating…' : gs.kill_switch ? 'Disable' : 'Enable'}
                </button>
              </div>
            )}

            {gs !== undefined && (
              <div className="stat-cards-row">
                <div className="stat-card">
                  <div className="stat-card__label">Day spent</div>
                  <div className="stat-card__value">{fmtUsd(gs.day_spent)}</div>
                  <div className="stat-card__sub">cap: {fmtUsd(gs.day_cap)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card__label">Month spent</div>
                  <div className="stat-card__value">{fmtUsd(gs.month_spent)}</div>
                  <div className="stat-card__sub">cap: {fmtUsd(gs.month_cap)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card__label">Day remaining</div>
                  <div className="stat-card__value">{fmtUsd(Math.max(0, gs.day_cap - gs.day_spent))}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-card__label">Month remaining</div>
                  <div className="stat-card__value">{fmtUsd(Math.max(0, gs.month_cap - gs.month_spent))}</div>
                </div>
              </div>
            )}

            <h2 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: 'var(--space-3)' }}>
              Daily spend — last 7 days
            </h2>
            <SpendChart rows={data.rows} />

            {data.rows.length > 0 && (
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Day</th>
                      <th>Purpose</th>
                      <th>Calls</th>
                      <th>Input tokens</th>
                      <th>Output tokens</th>
                      <th>Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.day}</td>
                        <td>{r.purpose}</td>
                        <td>{r.call_count}</td>
                        <td>{r.input_tokens.toLocaleString()}</td>
                        <td>{r.output_tokens.toLocaleString()}</td>
                        <td>{fmtUsd(r.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
