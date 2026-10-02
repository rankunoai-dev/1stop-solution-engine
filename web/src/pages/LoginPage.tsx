import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setCsrfToken } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type Step = 'email' | 'code' | 'sent'

export function LoginPage() {
  const navigate = useNavigate()
  const { setUser } = useAuth()

  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleRequestCode(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await api.requestCode(email)
      setStep('code')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send code')
    } finally {
      setLoading(false)
    }
  }

  async function handleVerifyCode(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const resp = await api.verifyCode(email, code)
      setCsrfToken(resp.csrf_token)
      setUser(resp.user)
      void navigate('/chat', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid code')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-card__title">1Stop</h1>
        {step === 'email' ? (
          <>
            <p className="login-card__subtitle">Enter your work email to sign in.</p>
            <form className="login-card__form" onSubmit={(e) => { void handleRequestCode(e) }}>
              <div className="form-group">
                <label htmlFor="email" className="form-label">Email address</label>
                <input
                  id="email"
                  type="email"
                  className="form-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@rankuno.com"
                  required
                  autoFocus
                />
              </div>
              {error !== null && <p className="form-error">{error}</p>}
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading || email.length === 0}
              >
                {loading ? 'Sending…' : 'Send code'}
              </button>
            </form>
          </>
        ) : (
          <>
            <p className="login-card__subtitle">
              Check your email at <strong>{email}</strong>. Enter the 6-digit code below.
            </p>
            <form className="login-card__form" onSubmit={(e) => { void handleVerifyCode(e) }}>
              <div className="form-group">
                <label htmlFor="code" className="form-label">One-time code</label>
                <input
                  id="code"
                  type="text"
                  className="form-input"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="000000"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  autoComplete="one-time-code"
                  autoFocus
                  required
                />
              </div>
              {error !== null && <p className="form-error">{error}</p>}
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading || code.length !== 6}
              >
                {loading ? 'Verifying…' : 'Verify'}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => { setStep('email'); setCode(''); setError(null) }}
              >
                Use a different email
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
