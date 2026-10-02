import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
  createElement,
} from 'react'
import { api } from '../api/client'
import type { UserInfo } from '../api/types'

interface AuthState {
  user: UserInfo | null
  loading: boolean
  logout: () => Promise<void>
  setUser: (u: UserInfo | null) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then((u) => {
        setUser(u)
      })
      .catch(() => {
        setUser(null)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // ignore errors on logout
    }
    setUser(null)
    window.location.href = '/login'
  }, [])

  return createElement(
    AuthContext.Provider,
    { value: { user, loading, logout, setUser } },
    children,
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
