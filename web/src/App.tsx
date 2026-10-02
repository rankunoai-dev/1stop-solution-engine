import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AdminRoute } from './components/AdminRoute'
import { LoginPage } from './pages/LoginPage'
import { ChatPage } from './pages/ChatPage'
import { AdminUsersPage } from './pages/admin/AdminUsersPage'
import { AdminSpendPage } from './pages/admin/AdminSpendPage'
import { AdminJobsPage } from './pages/admin/AdminJobsPage'

export function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/chat"
            element={
              <ProtectedRoute>
                <ChatPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminRoute>
                <AdminUsersPage />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/spend"
            element={
              <AdminRoute>
                <AdminSpendPage />
              </AdminRoute>
            }
          />
          <Route
            path="/admin/jobs"
            element={
              <AdminRoute>
                <AdminJobsPage />
              </AdminRoute>
            }
          />
          <Route path="/" element={<Navigate to="/chat" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  )
}
