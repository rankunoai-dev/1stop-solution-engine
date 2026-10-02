import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

interface Props {
  children: ReactNode
}

export function ProtectedRoute({ children }: Props) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="loading-screen">
        <span>Loading…</span>
      </div>
    )
  }

  if (user === null) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}
