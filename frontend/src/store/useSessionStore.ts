import { create } from 'zustand'
import type { ConnectionStatus, KitchenTimer, RecipeState, TranscriptLine, TranscriptRole } from '../types'

let nextLineId = 0

interface SessionStore {
  status: ConnectionStatus
  micLive: boolean
  cameraLive: boolean
  transcript: TranscriptLine[]
  recipeState: RecipeState | null
  timers: Record<string, KitchenTimer>

  setStatus: (status: ConnectionStatus) => void
  setMicLive: (live: boolean) => void
  setCameraLive: (live: boolean) => void
  appendTranscript: (role: TranscriptRole, text: string, opts?: { newLine?: boolean }) => void
  resetTranscriptCursor: () => void
  applySnapshot: (state: RecipeState) => void
  upsertTimer: (timer: KitchenTimer) => void
}

// Tracks whether the next appended chunk should start a new bubble or
// continue the last one — mirrors the streaming-transcript behavior of the
// vanilla client (static/app.js).
let lastRole: TranscriptRole | null = null

export const useSessionStore = create<SessionStore>((set) => ({
  status: 'connecting',
  micLive: false,
  cameraLive: false,
  transcript: [],
  recipeState: null,
  timers: {},

  setStatus: (status) => set({ status }),
  setMicLive: (micLive) => set({ micLive }),
  setCameraLive: (cameraLive) => set({ cameraLive }),

  appendTranscript: (role, text, opts) =>
    set((s) => {
      const startNew = opts?.newLine || lastRole !== role || s.transcript.length === 0
      lastRole = role
      if (startNew) {
        return { transcript: [...s.transcript, { id: nextLineId++, role, text }] }
      }
      const transcript = s.transcript.slice()
      const last = transcript[transcript.length - 1]
      transcript[transcript.length - 1] = { ...last, text: last.text + text }
      return { transcript }
    }),

  resetTranscriptCursor: () => {
    lastRole = null
  },

  applySnapshot: (state) => set({ recipeState: state, timers: state.active_timers || {} }),

  upsertTimer: (timer) =>
    set((s) => ({ timers: { ...s.timers, [timer.id]: timer } })),
}))
