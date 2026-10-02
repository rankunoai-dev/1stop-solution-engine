import type { SSEEvent } from './types'
import { getCsrfToken } from './client'

export function parseSSEEvent(raw: string): SSEEvent | null {
  const lines = raw.split('\n')
  let dataLine: string | undefined
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      dataLine = line.slice(6)
      break
    }
  }
  if (dataLine === undefined) return null
  try {
    return JSON.parse(dataLine) as SSEEvent
  } catch {
    return null
  }
}

export async function* streamChat(
  message: string,
  options: { model?: string; max_tokens?: number } = {},
): AsyncGenerator<SSEEvent> {
  const token = getCsrfToken()
  const res = await fetch('/api/v1/chat', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token !== null ? { 'X-CSRF-Token': token } : {}),
    },
    body: JSON.stringify({ message, ...options }),
  })
  if (!res.ok || res.body === null) throw new Error('Chat request failed')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const event = parseSSEEvent(part.trim())
      if (event !== null) yield event
    }
  }
  // Flush any remaining buffer
  if (buffer.trim().length > 0) {
    const event = parseSSEEvent(buffer.trim())
    if (event !== null) yield event
  }
}
