import { useEffect, useState, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NavBar } from '../../components/NavBar'
import { api } from '../../api/client'
import type { JobRow } from '../../api/types'

const POLL_INTERVAL = 10_000

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

const TERMINAL_STATUSES = new Set(['dead', 'failed'])

export function AdminJobsPage() {
  const location = useLocation()
  const [jobs, setJobs] = useState<JobRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [retrying, setRetrying] = useState<Set<string>>(new Set())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    void load()
    intervalRef.current = setInterval(() => { void load() }, POLL_INTERVAL)
    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current)
    }
  }, [statusFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  async function load() {
    try {
      const data = await api.adminJobs(statusFilter || undefined)
      setJobs(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs')
    } finally {
      setLoading(false)
    }
  }

  async function handleRetry(id: string) {
    setRetrying((prev) => new Set(prev).add(id))
    try {
      const updated = await api.retryJob(id)
      setJobs((prev) => prev.map((j) => (j.id === id ? updated : j)))
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to retry job')
    } finally {
      setRetrying((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

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

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>Jobs ({jobs.length}) — auto-refresh every 10s</h2>
          <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
            <label htmlFor="status-filter" style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
              Filter:
            </label>
            <select
              id="status-filter"
              className="form-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All</option>
              <option value="pending">pending</option>
              <option value="running">running</option>
              <option value="done">done</option>
              <option value="failed">failed</option>
              <option value="dead">dead</option>
            </select>
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => { void load() }}>
              Refresh
            </button>
          </div>
        </div>

        {loading && <p style={{ color: 'var(--color-text-muted)' }}>Loading…</p>}
        {error !== null && <p className="form-error">{error}</p>}

        {!loading && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Created</th>
                  <th>Run after</th>
                  <th>Error</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem' }}>{j.kind}</td>
                    <td>
                      <span className={`badge badge--${j.status}`}>{j.status}</span>
                    </td>
                    <td>{j.attempts}/{j.max_attempts}</td>
                    <td>{fmtDate(j.created_at)}</td>
                    <td>{fmtDate(j.run_after)}</td>
                    <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.8125rem', color: 'var(--color-error)' }}>
                      {j.error ?? '—'}
                    </td>
                    <td>
                      {TERMINAL_STATUSES.has(j.status) && (
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          disabled={retrying.has(j.id)}
                          onClick={() => { void handleRetry(j.id) }}
                        >
                          {retrying.has(j.id) ? 'Retrying…' : 'Retry'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--color-text-muted)' }}>
                      No jobs found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
