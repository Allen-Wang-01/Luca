// Short, recognizable name for a cited page - its site (e.g. "reuters.com") rather than
// the full URL, which is too long to show beside a caption.
export function sourceLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
