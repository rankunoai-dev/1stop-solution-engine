import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { createElement } from 'react'
import { LoginPage } from '../src/pages/LoginPage'
import { AuthProvider } from '../src/hooks/useAuth'
import * as client from '../src/api/client'

// Mock navigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

function renderLoginPage() {
  return render(
    createElement(
      MemoryRouter,
      { initialEntries: ['/login'] },
      createElement(AuthProvider, null, createElement(LoginPage, null)),
    ),
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    // Mock api.me() to return 401 (not logged in)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Not authenticated' }),
        statusText: 'Unauthorized',
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows email input in step 1', () => {
    renderLoginPage()
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send code/i })).toBeInTheDocument()
  })

  it('advances to step 2 after requestCode resolves', async () => {
    // First call: api.me() → 401; second call: requestCode → 200
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Not authenticated' }),
        statusText: 'Unauthorized',
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
    vi.stubGlobal('fetch', fetchMock)

    renderLoginPage()

    const emailInput = screen.getByLabelText(/email address/i)
    fireEvent.change(emailInput, { target: { value: 'test@rankuno.com' } })
    fireEvent.click(screen.getByRole('button', { name: /send code/i }))

    await waitFor(() => {
      expect(screen.getByLabelText(/one-time code/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/check your email/i)).toBeInTheDocument()
  })

  it('stores csrf token and navigates on successful verify', async () => {
    const mockUser = { id: 'u1', email: 'test@rankuno.com', role: 'staff' as const, display_name: null }
    const fetchMock = vi.fn()
      // api.me() → 401
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Not authenticated' }),
        statusText: 'Unauthorized',
      })
      // requestCode → 200
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      // verifyCode → 200
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ csrf_token: 'tok123', user: mockUser }),
      })
    vi.stubGlobal('fetch', fetchMock)

    const setCsrfSpy = vi.spyOn(client, 'setCsrfToken')
    renderLoginPage()

    // Step 1: send email
    const emailInput = screen.getByLabelText(/email address/i)
    fireEvent.change(emailInput, { target: { value: 'test@rankuno.com' } })
    fireEvent.click(screen.getByRole('button', { name: /send code/i }))

    await waitFor(() => screen.getByLabelText(/one-time code/i))

    // Step 2: enter code
    const codeInput = screen.getByLabelText(/one-time code/i)
    fireEvent.change(codeInput, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /verify/i }))

    await waitFor(() => {
      expect(setCsrfSpy).toHaveBeenCalledWith('tok123')
      expect(mockNavigate).toHaveBeenCalledWith('/chat', { replace: true })
    })
  })

  it('shows error message on verifyCode 422', async () => {
    const fetchMock = vi.fn()
      // api.me() → 401
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve({ detail: 'Not authenticated' }),
        statusText: 'Unauthorized',
      })
      // requestCode → 200
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
      // verifyCode → 422
      .mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: () => Promise.resolve({ detail: 'Invalid or expired code' }),
        statusText: 'Unprocessable Entity',
      })
    vi.stubGlobal('fetch', fetchMock)

    renderLoginPage()

    const emailInput = screen.getByLabelText(/email address/i)
    fireEvent.change(emailInput, { target: { value: 'test@rankuno.com' } })
    fireEvent.click(screen.getByRole('button', { name: /send code/i }))

    await waitFor(() => screen.getByLabelText(/one-time code/i))

    const codeInput = screen.getByLabelText(/one-time code/i)
    fireEvent.change(codeInput, { target: { value: '999999' } })
    fireEvent.click(screen.getByRole('button', { name: /verify/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired code/i)).toBeInTheDocument()
    })
  })
})
