// Stub for the real narration script an LLM-driven generation step will eventually
// produce. Same shape either way, so the sync engine built against this stub needs no
// changes once that real generator lands.
export interface NarrationLine {
  text: string
  target_id: string
}

export type NarrationScript = NarrationLine[]
