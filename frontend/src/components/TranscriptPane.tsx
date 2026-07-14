import { useEffect, useRef } from 'react'
import { useSessionStore } from '../store/useSessionStore'

const ROLE_STYLE: Record<string, string> = {
  user: 'text-white/90 text-right',
  agent: 'text-kitchen-accent text-left',
  error: 'text-kitchen-danger text-left',
}

export function TranscriptPane() {
  const transcript = useSessionStore((s) => s.transcript)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [transcript])

  return (
    <section className="flex h-64 flex-col overflow-y-auto rounded-xl bg-kitchen-panel p-4">
      {transcript.length === 0 && (
        <p className="m-auto text-sm text-white/40">Say something to start the conversation.</p>
      )}
      {transcript.map((line) => (
        <p key={line.id} className={`mb-2 text-sm ${ROLE_STYLE[line.role] ?? 'text-white/80'}`}>
          {line.text}
        </p>
      ))}
      <div ref={bottomRef} />
    </section>
  )
}
