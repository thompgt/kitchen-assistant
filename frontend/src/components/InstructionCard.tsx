import { useSessionStore } from '../store/useSessionStore'

export function InstructionCard() {
  const recipeState = useSessionStore((s) => s.recipeState)
  const recipe = recipeState?.recipe_metadata

  if (!recipe) {
    return (
      <section className="rounded-xl bg-kitchen-panel p-8 text-center text-white/50">
        No recipe loaded — say "find me a recipe" to get started.
      </section>
    )
  }

  const stepIndex = recipeState?.current_step_index ?? 0
  const step = recipe.steps[stepIndex]
  const total = recipe.steps.length

  return (
    <section className="rounded-xl bg-kitchen-panel p-8">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-xl font-semibold text-white">{recipe.title}</h2>
        <span className="text-sm text-white/50">
          Step {stepIndex + 1} of {total}
        </span>
      </div>
      <p className="text-[28px] font-medium leading-snug text-white">
        {step ? step.instruction : 'Recipe complete.'}
      </p>
    </section>
  )
}
