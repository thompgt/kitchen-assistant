import { useSessionStore } from '../store/useSessionStore'

const STATUS_COLOR: Record<string, string> = {
  listening: 'bg-kitchen-ok',
  thinking: 'bg-kitchen-accent animate-pulse',
  speaking: 'bg-kitchen-accent',
  connecting: 'bg-gray-500 animate-pulse',
  closed: 'bg-kitchen-danger',
}

export function StatusBar() {
  const status = useSessionStore((s) => s.status)
  const dotClass = STATUS_COLOR[status] ?? 'bg-gray-500'

  return (
    <header className="flex items-center justify-between border-b border-white/10 px-6 py-3">
      <h1 className="text-lg font-semibold tracking-wide text-white">Kitchen Assistant</h1>
      <div className="flex items-center gap-2">
        <span className={`h-3 w-3 rounded-full ${dotClass}`} />
        <span className="text-sm uppercase tracking-widest text-white/70">{status}</span>
      </div>
    </header>
  )
}
