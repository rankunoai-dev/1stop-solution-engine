// Auth
export interface UserInfo {
  id: string
  email: string
  role: 'staff' | 'admin'
  display_name: string | null
}
export interface VerifyCodeResponse {
  csrf_token: string
  user: UserInfo
}

// Chat SSE events
export type SSEEvent =
  | { type: 'status'; state: string; conversation_id: string }
  | { type: 'token'; text: string; conversation_id: string }
  | { type: 'done'; conversation_id: string; input_tokens: number; output_tokens: number; cost_usd: number }
  | { type: 'error'; code: string; detail: string; conversation_id: string }

// Admin
export interface UserRow {
  id: string
  email: string
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string
  last_login_at: string | null
  active_sessions: number
  llm_call_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost_usd: number
}
export interface SpendRow {
  day: string
  purpose: string
  call_count: number
  input_tokens: number
  output_tokens: number
  cost_usd: number
}
export interface SpendResponse {
  rows: SpendRow[]
  guard_status: {
    day_spent: number
    month_spent: number
    day_cap: number
    month_cap: number
    kill_switch: boolean
  }
}
export interface JobRow {
  id: string
  kind: string
  status: string
  attempts: number
  max_attempts: number
  run_after: string
  created_at: string
  error: string | null
}
