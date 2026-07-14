// Mirrors app/schemas.py — kept in sync manually until an OpenAPI/codegen
// step exists (Phase 7 backlog).

export interface Ingredient {
  name: string
  amount: number
  unit: string
}

export interface RecipeStep {
  step_number: number
  instruction: string
  duration_minutes: number | null
}

export interface RecipeMetadata {
  id: string
  title: string
  description: string | null
  ingredients: Ingredient[]
  steps: RecipeStep[]
  total_time_minutes: number
}

export interface KitchenTimer {
  id: string
  label: string
  duration_seconds: number
  start_time: string
  remaining_seconds: number
  is_active: boolean
}

export interface RecipeState {
  session_id: string
  recipe_id: string | null
  recipe_metadata: RecipeMetadata | null
  current_step_index: number
  active_timers: Record<string, KitchenTimer>
  servings_multiplier: number
  last_updated: string
}

export type ConnectionStatus = 'connecting' | 'listening' | 'thinking' | 'speaking' | 'closed' | string

export type TranscriptRole = 'user' | 'agent' | 'error'

export interface TranscriptLine {
  id: number
  role: TranscriptRole
  text: string
}

export type ServerEnvelope =
  | { type: 'session.status'; status: ConnectionStatus }
  | { type: 'transcript.user'; text: string }
  | { type: 'transcript.agent'; text: string }
  | { type: 'interrupted' }
  | { type: 'state.snapshot'; state: RecipeState }
  | { type: 'timer.update'; timer: KitchenTimer }
  | { type: 'timer.expired'; timer: KitchenTimer }
  | { type: 'error'; message: string }
