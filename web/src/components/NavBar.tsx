import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function NavBar() {
  const { user, logout } = useAuth()
  const location = useLocation()

  const isActive = (path: string) => location.pathname.startsWith(path)

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <Link to="/chat" className="navbar-logo">
          1Stop
        </Link>
      </div>
      <div className="navbar-links">
        <Link
          to="/chat"
          className={`navbar-link${isActive('/chat') ? ' active' : ''}`}
        >
          Chat
        </Link>
        {user?.role === 'admin' && (
          <>
            <Link
              to="/admin/users"
              className={`navbar-link${isActive('/admin') ? ' active' : ''}`}
            >
              Admin
            </Link>
          </>
        )}
        <button
          type="button"
          className="navbar-logout"
          onClick={() => { void logout() }}
        >
          Logout
        </button>
      </div>
    </nav>
  )
}
