import type { UserInfo, UserRow, SpendResponse, JobRow } from './types'

const BASE = '/api/v1'

let csrfToken: string | null = null
export function setCsrfToken(t: string): void {
  csrfToken = t
}
export function getCsrfToken(): string | null {
  return csrfToken
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  }
  if (csrfToken && init.method && init.method !== 'GET') {
    headers['X-CSRF-Token'] = csrfToken
  }
  const res = await fetch(BASE + path, { ...init, credentials: 'include', headers })
  if (res.status === 401) {
    window.location.href = '/login'
    throw new Error('Unauthenticated')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? res.statusText)
  }
  return res.json() as Promise<T>
}

export const api = {
  requestCode: (email: string) =>
    apiFetch<Record<string, never>>('/auth/request-code', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  verifyCode: (email: string, code: string) =>
    apiFetch<{ csrf_token: string; user: UserInfo }>('/auth/verify-code', {
      method: 'POST',
      body: JSON.stringify({ email, code }),
    }),
  logout: () =>
    apiFetch<Record<string, never>>('/auth/logout', { method: 'POST' }),
  me: () => apiFetch<UserInfo>('/me'),
  adminUsers: () => apiFetch<UserRow[]>('/admin/users'),
  createUser: (data: { email: string; display_name?: string; role?: string }) =>
    apiFetch<UserRow>('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  patchUser: (
    id: string,
    data: Partial<{ is_active: boolean; role: string; display_name: string }>,
  ) =>
    apiFetch<UserRow>(`/admin/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  adminSpend: (days?: number) =>
    apiFetch<SpendResponse>(`/admin/spend${days !== undefined ? `?days=${days}` : ''}`),
  setKillSwitch: (enabled: boolean) =>
    apiFetch<Record<string, never>>('/admin/spend/kill-switch', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  adminJobs: (status?: string) =>
    apiFetch<JobRow[]>(`/admin/jobs${status !== undefined ? `?status=${status}` : ''}`),
  retryJob: (id: string) =>
    apiFetch<JobRow>(`/admin/jobs/${id}/retry`, { method: 'POST', body: '{}' }),
}
