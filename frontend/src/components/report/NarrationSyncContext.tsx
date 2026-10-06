import { createContext, useContext, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { ancestorIds, type NarrationTarget, type TargetIndex } from '../../narration/targetIndex'

// - 'active': the narration target itself
// - 'focus': contains the target (its table, or the row of a targeted cell) - stays lit
// - 'within': inside the target (the cells of a targeted row) - lit along with it
// - 'dimmed': unrelated to the target
// - 'neutral': nothing is being narrated
export type SyncState = 'active' | 'focus' | 'within' | 'dimmed' | 'neutral'

interface NarrationSyncApi {
  activeId: string | null
  activeTarget: NarrationTarget | undefined
  resolveState: (id: string) => SyncState
  registerRef: (id: string) => (el: HTMLElement | null) => void
  getElement: (id: string) => HTMLElement | undefined
}

const NarrationSyncContext = createContext<NarrationSyncApi | null>(null)

interface NarrationSyncProviderProps {
  activeId: string | null
  // Looked up rather than inferred from id prefixes: a cell id continues its row id
  // with a single "_", which a prefix check can't tell apart from a longer sibling id.
  targets: TargetIndex
  children: ReactNode
}

export function NarrationSyncProvider({ activeId, targets, children }: NarrationSyncProviderProps) {
  // Stable across renders: a Map of ids to DOM nodes, plus one memoized ref-callback
  // per id so passing `ref={registerRef(id)}` doesn't churn identity every render.
  const registryRef = useRef<{
    elements: Map<string, HTMLElement>
    callbacks: Map<string, (el: HTMLElement | null) => void>
  } | null>(null)
  if (!registryRef.current) {
    registryRef.current = { elements: new Map(), callbacks: new Map() }
  }

  const registerRef = useMemo(() => {
    return (id: string) => {
      const { elements, callbacks } = registryRef.current!
      let callback = callbacks.get(id)
      if (!callback) {
        callback = (el) => {
          if (el) elements.set(id, el)
          else elements.delete(id)
        }
        callbacks.set(id, callback)
      }
      return callback
    }
    // registryRef itself never changes identity, so this factory is stable for the
    // provider's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const value = useMemo<NarrationSyncApi>(() => {
    const activeTarget = activeId === null ? undefined : targets.get(activeId)
    const activeAncestors = ancestorIds(activeTarget)
    return {
      activeId,
      activeTarget,
      resolveState: (id) => {
        if (activeId === null) return 'neutral'
        if (activeId === id) return 'active'
        if (activeAncestors.includes(id)) return 'focus'
        if (ancestorIds(targets.get(id)).includes(activeId)) return 'within'
        return 'dimmed'
      },
      registerRef,
      getElement: (id) => registryRef.current!.elements.get(id),
    }
  }, [activeId, targets, registerRef])

  return <NarrationSyncContext.Provider value={value}>{children}</NarrationSyncContext.Provider>
}

export function useNarrationSync(): NarrationSyncApi {
  const ctx = useContext(NarrationSyncContext)
  if (!ctx) {
    throw new Error('useNarrationSync must be used within a NarrationSyncProvider')
  }
  return ctx
}

// Convenience for block/row/cell components: the ref to register their DOM node under
// their own id, plus the sync state to drive under a `data-sync` attribute.
export function useSyncTarget(id: string): { ref: (el: HTMLElement | null) => void; state: SyncState } {
  const { resolveState, registerRef } = useNarrationSync()
  return { ref: registerRef(id), state: resolveState(id) }
}
