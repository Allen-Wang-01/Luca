import { createContext, useContext, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'

export type SyncState = 'active' | 'focus' | 'dimmed' | 'neutral'

interface NarrationSyncApi {
  activeId: string | null
  registerRef: (id: string) => (el: HTMLElement | null) => void
  getElement: (id: string) => HTMLElement | undefined
}

const NarrationSyncContext = createContext<NarrationSyncApi | null>(null)

// Row/cell ids are always `{block_id}__...` (see docs/schema.md), so containment is a
// prefix check - no separate parent lookup needed to know a block should stay "in
// focus" (not dimmed) while one of its own rows/cells is the actual target.
function resolveSyncState(id: string, activeId: string | null): SyncState {
  if (activeId === null) return 'neutral'
  if (activeId === id) return 'active'
  if (activeId.startsWith(`${id}__`)) return 'focus'
  return 'dimmed'
}

interface NarrationSyncProviderProps {
  activeId: string | null
  children: ReactNode
}

export function NarrationSyncProvider({ activeId, children }: NarrationSyncProviderProps) {
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

  const value = useMemo<NarrationSyncApi>(
    () => ({
      activeId,
      registerRef,
      getElement: (id) => registryRef.current!.elements.get(id),
    }),
    [activeId, registerRef],
  )

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
  const { activeId, registerRef } = useNarrationSync()
  return { ref: registerRef(id), state: resolveSyncState(id, activeId) }
}
