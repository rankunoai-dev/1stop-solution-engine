import { useState, useCallback, useRef } from 'react'
import { streamChat } from '../api/sse'
import type { SSEEvent } from '../api/types'

type SSEStatus = 'idle' | 'connecting' | 'streaming' | 'done' | 'error'

interface SSEHookResult {
  events: SSEEvent[]
  status: SSEStatus
  send: (message: string, options?: { model?: string; max_tokens?: number }) => void
  reset: () => void
}

export function useSSE(): SSEHookResult {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [status, setStatus] = useState<SSEStatus>('idle')
  const abortRef = useRef<boolean>(false)

  const reset = useCallback(() => {
    setEvents([])
    setStatus('idle')
    abortRef.current = false
  }, [])

  const send = useCallback(
    (message: string, options?: { model?: string; max_tokens?: number }) => {
      abortRef.current = false
      setEvents([])
      setStatus('connecting')

      void (async () => {
        try {
          setStatus('streaming')
          for await (const event of streamChat(message, options ?? {})) {
            if (abortRef.current) break
            setEvents((prev) => [...prev, event])
            if (event.type === 'done' || event.type === 'error') {
              setStatus(event.type === 'done' ? 'done' : 'error')
              break
            }
          }
          if (!abortRef.current) {
            setStatus((s) => (s === 'streaming' ? 'done' : s))
          }
        } catch {
          if (!abortRef.current) {
            setStatus('error')
          }
        }
      })()
    },
    [],
  )

  return { events, status, send, reset }
}
