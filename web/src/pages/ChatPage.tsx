import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { NavBar } from '../components/NavBar'
import { MessageBubble } from '../components/MessageBubble'
import { streamChat } from '../api/sse'
import type { SSEEvent } from '../api/types'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  isError: boolean
}

interface PendingState {
  text: string
  statusLabel: string
  conversationId: string | null
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState<PendingState | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, pending])

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!sending && input.trim().length > 0) {
        void sendMessage()
      }
    }
  }

  async function sendMessage() {
    const text = input.trim()
    if (text.length === 0 || sending) return
    setInput('')
    setSending(true)

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      text,
      isError: false,
    }
    setMessages((prev) => [...prev, userMsg])

    setPending({ text: '', statusLabel: 'connecting…', conversationId: null })

    try {
      for await (const event of streamChat(text)) {
        handleSSEEvent(event)
      }
    } catch {
      setPending(null)
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          text: 'Connection error. Please try again.',
          isError: true,
        },
      ])
    } finally {
      setSending(false)
    }
  }

  function handleSSEEvent(event: SSEEvent) {
    switch (event.type) {
      case 'status':
        setPending((p) =>
          p !== null
            ? { ...p, statusLabel: event.state, conversationId: event.conversation_id }
            : null,
        )
        break
      case 'token':
        setPending((p) =>
          p !== null
            ? {
                ...p,
                text: p.text + event.text,
                statusLabel: 'answering…',
                conversationId: event.conversation_id,
              }
            : null,
        )
        break
      case 'done':
        setPending((p) => {
          if (p !== null) {
            setMessages((msgs) => [
              ...msgs,
              {
                id: crypto.randomUUID(),
                role: 'assistant',
                text: p.text,
                isError: false,
              },
            ])
          }
          return null
        })
        break
      case 'error':
        setPending(null)
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            text: `Error: ${event.detail}`,
            isError: true,
          },
        ])
        break
    }
  }

  return (
    <div className="page-shell">
      <NavBar />
      <div className="chat-page">
        <div className="chat-messages">
          {messages.length === 0 && pending === null && (
            <div className="chat-empty">Ask anything about RankUno tools.</div>
          )}
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              role={m.role}
              text={m.text}
              isError={m.isError}
            />
          ))}
          {pending !== null && (
            <MessageBubble
              role="assistant"
              text={pending.text}
              pending
              statusLabel={pending.statusLabel}
            />
          )}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input-bar">
          <textarea
            className="chat-textarea"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a RankUno tool… (Enter to send, Shift+Enter for newline)"
            rows={1}
            disabled={sending}
          />
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => { void sendMessage() }}
            disabled={sending || input.trim().length === 0}
          >
            {sending ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
