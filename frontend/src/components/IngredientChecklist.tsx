import { useSessionStore } from '../store/useSessionStore'

function formatAmount(amount: number): string {
  const rounded = Math.round(amount * 100) / 100
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2)
}

export function IngredientChecklist() {
  const recipeState = useSessionStore((s) => s.recipeState)
  const recipe = recipeState?.recipe_metadata
  const multiplier = recipeState?.servings_multiplier ?? 1

  if (!recipe) return null

  return (
    <section className="rounded-xl bg-kitchen-panel p-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-base font-semibold text-white/90">Ingredients</h3>
        {multiplier !== 1 && (
          <span className="text-xs text-kitchen-accent">×{formatAmount(multiplier)}</span>
        )}
      </div>
      <ul className="space-y-2">
        {recipe.ingredients.map((ing) => (
          <li key={ing.name} className="flex justify-between text-sm text-white/80">
            <span>{ing.name}</span>
            <span className="text-white/50">
              {formatAmount(ing.amount * multiplier)} {ing.unit}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
