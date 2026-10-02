import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSSE } from '../src/hooks/useSSE'
import * as sseModule from '../src/api/sse'
import type { SSEEvent } from '../src/api/types'

describe('useSSE / streamChat accumulation', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('accumulates token texts from status → token × 3 → done sequence', async () => {
    const mockEvents: SSEEvent[] = [
      { type: 'status', state: 'thinking', conversation_id: 'c1' },
      { type: 'token', text: 'Hello', conversation_id: 'c1' },
      { type: 'token', text: ' world', conversation_id: 'c1' },
      { type: 'token', text: '!', conversation_id: 'c1' },
      { type: 'done', conversation_id: 'c1', input_tokens: 5, output_tokens: 10, cost_usd: 0.0001 },
    ]

    // Mock streamChat to yield the mock events
    vi.spyOn(sseModule, 'streamChat').mockImplementation(async function* () {
      for (const event of mockEvents) {
        yield event
      }
    })

    const { result } = renderHook(() => useSSE())

    await act(async () => {
      result.current.send('test message')
      // Wait for all events to be processed
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    expect(result.current.status).toBe('done')
    expect(result.current.events).toHaveLength(5)

    // Check status event
    expect(result.current.events[0]).toMatchObject({ type: 'status', state: 'thinking' })

    // Check token events
    const tokenEvents = result.current.events.filter((e) => e.type === 'token')
    expect(tokenEvents).toHaveLength(3)

    // Verify done event captured
    const doneEvent = result.current.events.find((e) => e.type === 'done')
    expect(doneEvent).toMatchObject({ type: 'done', conversation_id: 'c1', input_tokens: 5, output_tokens: 10 })
  })

  it('sets status to error when streamChat throws', async () => {
    vi.spyOn(sseModule, 'streamChat').mockImplementation(async function* () {
      throw new Error('Connection failed')
      // eslint-disable-next-line no-unreachable
      yield {} as SSEEvent
    })

    const { result } = renderHook(() => useSSE())

    await act(async () => {
      result.current.send('test message')
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    expect(result.current.status).toBe('error')
  })

  it('handles error event from stream', async () => {
    const mockEvents: SSEEvent[] = [
      { type: 'status', state: 'thinking', conversation_id: 'c1' },
      { type: 'error', code: 'cap_exceeded', detail: 'Daily cap exceeded', conversation_id: 'c1' },
    ]

    vi.spyOn(sseModule, 'streamChat').mockImplementation(async function* () {
      for (const event of mockEvents) {
        yield event
      }
    })

    const { result } = renderHook(() => useSSE())

    await act(async () => {
      result.current.send('test message')
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    expect(result.current.status).toBe('error')
    const errorEvent = result.current.events.find((e) => e.type === 'error')
    expect(errorEvent).toMatchObject({ type: 'error', code: 'cap_exceeded' })
  })

  it('reset clears events and status', async () => {
    vi.spyOn(sseModule, 'streamChat').mockImplementation(async function* () {
      yield { type: 'done', conversation_id: 'c1', input_tokens: 1, output_tokens: 1, cost_usd: 0 } as SSEEvent
    })

    const { result } = renderHook(() => useSSE())

    await act(async () => {
      result.current.send('test')
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    expect(result.current.events.length).toBeGreaterThan(0)

    act(() => {
      result.current.reset()
    })

    expect(result.current.events).toHaveLength(0)
    expect(result.current.status).toBe('idle')
  })
})
