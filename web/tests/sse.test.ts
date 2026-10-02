import { describe, it, expect, vi, beforeEach } from 'vitest'
import { parseSSEEvent, streamChat } from '../src/api/sse'

describe('parseSSEEvent', () => {
  it('parses a token event', () => {
    const raw = 'data: {"type":"token","text":"hello","conversation_id":"x"}'
    const event = parseSSEEvent(raw)
    expect(event).toEqual({ type: 'token', text: 'hello', conversation_id: 'x' })
  })

  it('parses a status event', () => {
    const raw = 'data: {"type":"status","state":"thinking","conversation_id":"abc"}'
    const event = parseSSEEvent(raw)
    expect(event).toEqual({ type: 'status', state: 'thinking', conversation_id: 'abc' })
  })

  it('parses a done event', () => {
    const raw = 'data: {"type":"done","conversation_id":"c1","input_tokens":10,"output_tokens":20,"cost_usd":0.001}'
    const event = parseSSEEvent(raw)
    expect(event).toEqual({
      type: 'done',
      conversation_id: 'c1',
      input_tokens: 10,
      output_tokens: 20,
      cost_usd: 0.001,
    })
  })

  it('returns null for empty string', () => {
    expect(parseSSEEvent('')).toBeNull()
  })

  it('returns null for non-data line', () => {
    expect(parseSSEEvent('event: token')).toBeNull()
  })

  it('handles multiline block with event: and data: prefix — only parses data line', () => {
    const raw = 'event: token\ndata: {"type":"token","text":"hi","conversation_id":"x"}'
    const event = parseSSEEvent(raw)
    expect(event).toEqual({ type: 'token', text: 'hi', conversation_id: 'x' })
  })

  it('returns null for invalid JSON', () => {
    expect(parseSSEEvent('data: not-json')).toBeNull()
  })
})

describe('streamChat', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('yields all events from a streamed response', async () => {
    const events = [
      { type: 'status', state: 'thinking', conversation_id: 'c1' },
      { type: 'token', text: 'Hello', conversation_id: 'c1' },
      { type: 'token', text: ' world', conversation_id: 'c1' },
      { type: 'done', conversation_id: 'c1', input_tokens: 5, output_tokens: 10, cost_usd: 0.0001 },
    ]

    // Build SSE body: each event separated by double newline
    const body = events
      .map((e) => `data: ${JSON.stringify(e)}`)
      .join('\n\n')

    const encoder = new TextEncoder()
    const encoded = encoder.encode(body)

    // Mock fetch to return a ReadableStream
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(encoded)
            controller.close()
          },
        }),
      }),
    )

    const received = []
    for await (const event of streamChat('test message')) {
      received.push(event)
    }

    expect(received).toHaveLength(4)
    expect(received[0]).toEqual({ type: 'status', state: 'thinking', conversation_id: 'c1' })
    expect(received[1]).toEqual({ type: 'token', text: 'Hello', conversation_id: 'c1' })
    expect(received[2]).toEqual({ type: 'token', text: ' world', conversation_id: 'c1' })
    expect(received[3]).toMatchObject({ type: 'done', conversation_id: 'c1' })
  })

  it('throws when response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        body: null,
      }),
    )

    await expect(async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _ of streamChat('test')) {
        // do nothing
      }
    }).rejects.toThrow('Chat request failed')
  })

  it('handles chunked delivery (event split across chunks)', async () => {
    const event = { type: 'token', text: 'split', conversation_id: 'c2' }
    const fullChunk = `data: ${JSON.stringify(event)}\n\n`
    const half1 = fullChunk.slice(0, 10)
    const half2 = fullChunk.slice(10)
    const encoder = new TextEncoder()

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(half1))
            controller.enqueue(encoder.encode(half2))
            controller.close()
          },
        }),
      }),
    )

    const received = []
    for await (const e of streamChat('test')) {
      received.push(e)
    }

    expect(received).toHaveLength(1)
    expect(received[0]).toEqual(event)
  })
})
