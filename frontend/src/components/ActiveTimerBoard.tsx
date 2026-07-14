import { useEffect, useState } from 'react'
import { useSessionStore } from '../store/useSessionStore'
import type { KitchenTimer } from '../types'

function secondsLeft(timer: KitchenTimer, now: number): number {
  const end = new Date(timer.start_time).getTime() + timer.duration_seconds * 1000
  return Math.ceil((end - now) / 1000)
}

function formatClock(seconds: number): string {
  const clamped = Math.max(0, seconds)
  return `${Math.floor(clamped / 60)}:${String(clamped % 60).padStart(2, '0')}`
}

function TimerRing({ timer, now }: { timer: KitchenTimer; now: number }) {
  const left = secondsLeft(timer, now)
  const done = left <= 0
  const pct = Math.max(0, Math.min(1, left / timer.duration_seconds))
  const angle = pct * 360
  const ringColor = done ? '#ff5252' : left <= 10 ? '#ff5252' : '#ffb020'

  return (
    <div className="flex flex-col items-center gap-2 rounded-lg bg-black/20 p-4">
      <div
        className="flex h-20 w-20 items-center justify-center rounded-full text-lg font-semibold text-white"
        style={{
          background: `conic-gradient(${ringColor} ${angle}deg, rgba(255,255,255,0.1) ${angle}deg)`,
        }}
      >
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-kitchen-panel">
          {done ? '⏰' : formatClock(left)}
        </div>
      </div>
      <span className="max-w-[6rem] truncate text-center text-xs text-white/70">{timer.label}</span>
    </div>
  )
}

export function ActiveTimerBoard() {
  const timers = useSessionStore((s) => s.timers)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const active = Object.values(timers)
  if (active.length === 0) return null

  return (
    <section className="rounded-xl bg-kitchen-panel p-6">
      <h3 className="mb-3 text-base font-semibold text-white/90">Timers</h3>
      <div className="flex flex-wrap gap-4">
        {active.map((timer) => (
          <TimerRing key={timer.id} timer={timer} now={now} />
        ))}
      </div>
    </section>
  )
}
