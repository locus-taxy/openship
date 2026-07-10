import { useEffect, useState } from "react"
import api from "@/services"

export interface ExecutionResult {
  stdout: string
  stderr: string
}

// ── Runtime cache ─────────────────────────────────────────────────────────────

let _cache: Set<string> | null = null
const _listeners: Set<() => void> = new Set()

function _notify() {
  _listeners.forEach(fn => fn())
}

// Fetch once; notify all subscribers when done
let _fetching = false
function _warmCache() {
  if (_cache !== null || _fetching) return
  _fetching = true
  api.get<{ languages: string[] }>("/py/execute/runtimes")
    .then(res => {
      _cache = new Set(res.data.languages)
      _notify()
    })
    .catch(() => {
      // Transient failure: leave _cache unset so a later mount can retry,
      // rather than permanently caching "no runtimes".
      _fetching = false
    })
}

// Call once at app load (imported by executor users)
_warmCache()

// ── React hook ────────────────────────────────────────────────────────────────

export function useIsRunnable(language: string): boolean {
  const [runnable, setRunnable] = useState(() =>
    _cache ? _cache.has(language?.toLowerCase() ?? "") : false
  )

  useEffect(() => {
    // If cache already loaded, sync immediately
    if (_cache !== null) {
      setRunnable(_cache.has(language?.toLowerCase() ?? ""))
      return
    }
    // Cache not ready (or a prior fetch failed) — retry, then subscribe.
    _warmCache()
    const check = () => setRunnable(_cache!.has(language?.toLowerCase() ?? ""))
    _listeners.add(check)
    return () => { _listeners.delete(check) }
  }, [language])

  return runnable
}

// ── Execution ─────────────────────────────────────────────────────────────────

export async function executeCode(language: string, code: string): Promise<ExecutionResult> {
  const res = await api.post<ExecutionResult>("/py/execute", { language, code })
  return res.data
}
