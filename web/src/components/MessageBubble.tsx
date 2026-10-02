interface Props {
  role: 'user' | 'assistant'
  text: string
  pending?: boolean
  statusLabel?: string
  isError?: boolean
}

export function MessageBubble({ role, text, pending = false, statusLabel, isError = false }: Props) {
  return (
    <div className={`message-bubble message-bubble--${role}${isError ? ' message-bubble--error' : ''}`}>
      <div className="message-bubble__meta">
        <span className="message-bubble__role">{role === 'user' ? 'You' : '1Stop'}</span>
        {pending && statusLabel !== undefined && (
          <span className="message-bubble__status">{statusLabel}</span>
        )}
      </div>
      <div className="message-bubble__text">
        {text}
        {pending && <span className="message-bubble__cursor" aria-hidden="true" />}
      </div>
    </div>
  )
}
