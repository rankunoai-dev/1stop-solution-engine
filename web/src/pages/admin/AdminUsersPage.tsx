import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NavBar } from '../../components/NavBar'
import { api } from '../../api/client'
import type { UserRow } from '../../api/types'

function fmtDate(iso: string | null): string {
  if (iso === null) return '—'
  return new Date(iso).toLocaleString()
}

function fmtUsd(v: number): string {
  return `$${v.toFixed(4)}`
}

export function AdminUsersPage() {
  const location = useLocation()
  const [users, setUsers] = useState<UserRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create user form
  const [showCreate, setShowCreate] = useState(false)
  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')
  const [newRole, setNewRole] = useState<'staff' | 'admin'>('staff')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  useEffect(() => {
    void load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      const data = await api.adminUsers()
      setUsers(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  async function handleCreateUser() {
    setCreateError(null)
    setCreating(true)
    try {
      const u = await api.createUser({ email: newEmail, display_name: newName || undefined, role: newRole })
      setUsers((prev) => [...prev, u])
      setNewEmail('')
      setNewName('')
      setNewRole('staff')
      setShowCreate(false)
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  async function handlePatch(id: string, data: Partial<{ is_active: boolean; role: string }>) {
    try {
      const updated = await api.patchUser(id, data)
      setUsers((prev) => prev.map((u) => (u.id === id ? updated : u)))
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update user')
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
          <h2 style={{ fontSize: '1rem', fontWeight: 600 }}>Users ({users.length})</h2>
          <button type="button" className="btn btn--primary btn--sm" onClick={() => setShowCreate((s) => !s)}>
            {showCreate ? 'Cancel' : '+ Create user'}
          </button>
        </div>

        {showCreate && (
          <div className="inline-form">
            <div className="form-group">
              <label className="form-label">Email *</label>
              <input
                type="email"
                className="form-input"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="user@rankuno.com"
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Display name</label>
              <input
                type="text"
                className="form-input"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Optional"
              />
            </div>
            <div className="form-group">
              <label className="form-label">Role</label>
              <select
                className="form-select"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as 'staff' | 'admin')}
              >
                <option value="staff">staff</option>
                <option value="admin">admin</option>
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              {createError !== null && <p className="form-error">{createError}</p>}
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={creating || newEmail.length === 0}
                onClick={() => { void handleCreateUser() }}
              >
                {creating ? 'Creating…' : 'Create'}
              </button>
            </div>
          </div>
        )}

        {loading && <p style={{ color: 'var(--color-text-muted)' }}>Loading…</p>}
        {error !== null && <p className="form-error">{error}</p>}

        {!loading && (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Active</th>
                  <th>Sessions</th>
                  <th>LLM Calls</th>
                  <th>Cost</th>
                  <th>Last login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>{u.display_name ?? '—'}</td>
                    <td>
                      <select
                        className="form-select"
                        value={u.role}
                        onChange={(e) => { void handlePatch(u.id, { role: e.target.value }) }}
                      >
                        <option value="staff">staff</option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                    <td>
                      <span className={`badge badge--${u.is_active ? 'active' : 'inactive'}`}>
                        {u.is_active ? 'active' : 'inactive'}
                      </span>
                    </td>
                    <td>{u.active_sessions}</td>
                    <td>{u.llm_call_count}</td>
                    <td>{fmtUsd(u.total_cost_usd)}</td>
                    <td>{fmtDate(u.last_login_at)}</td>
                    <td>
                      <button
                        type="button"
                        className={`btn btn--sm ${u.is_active ? 'btn--danger' : 'btn--secondary'}`}
                        onClick={() => { void handlePatch(u.id, { is_active: !u.is_active }) }}
                      >
                        {u.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', color: 'var(--color-text-muted)' }}>
                      No users found.
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
