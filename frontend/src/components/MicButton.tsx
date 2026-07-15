import { useState } from 'react'
import { useSessionStore } from '../store/useSessionStore'

interface MicButtonProps {
  onToggle: () => void
  onToggleCamera: () => void
  onSendText: (text: string) => void
}

export function MicButton({ onToggle, onToggleCamera, onSendText }: MicButtonProps) {
  const micLive = useSessionStore((s) => s.micLive)
  const cameraLive = useSessionStore((s) => s.cameraLive)
  const [text, setText] = useState('')

  return (
    <div className="flex items-center gap-3 border-t border-white/10 px-6 py-4">
      <button
        onClick={onToggle}
        className={`rounded-full px-6 py-3 text-sm font-semibold transition-colors ${
          micLive
            ? 'animate-pulse bg-kitchen-danger text-white'
            : 'bg-kitchen-accent text-black hover:brightness-110'
        }`}
      >
        {micLive ? '⏹ Stop' : '🎤 Start'}
      </button>
      <button
        onClick={onToggleCamera}
        className={`rounded-full border px-4 py-3 text-sm font-semibold transition-colors ${
          cameraLive
            ? 'border-kitchen-accent text-kitchen-accent'
            : 'border-white/20 text-white/70 hover:border-white/40'
        }`}
      >
        {cameraLive ? '⏹ Camera' : '📷 Camera'}
      </button>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== 'Enter' || !text.trim()) return
          onSendText(text.trim())
          setText('')
        }}
        placeholder="Type instead of speaking…"
        className="flex-1 rounded-lg bg-black/30 px-4 py-2 text-sm text-white placeholder-white/30 outline-none focus:ring-2 focus:ring-kitchen-accent"
      />
    </div>
  )
}
