import { computed, type ComputedRef } from 'vue'

/**
 * Expose the runtime store's message array without creating a second mutable
 * copy inside the presentation component.
 */
export function useAuthoritativeMessages<T>(source: () => T[] | undefined): ComputedRef<T[]> {
  return computed(() => source() || [])
}
