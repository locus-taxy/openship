export interface ExecutionResult {
  stdout: string
  stderr: string
}

const RUNNABLE = new Set(["python", "javascript", "js"])

export function isRunnable(language: string): boolean {
  return RUNNABLE.has(language?.toLowerCase() ?? "")
}

// ── JavaScript: run in a Web Worker so it can't block the UI ─────────────────

function runJavaScript(code: string): Promise<ExecutionResult> {
  return new Promise((resolve) => {
    const logs: string[] = []
    const errs: string[] = []

    const workerSrc = `
      const _log   = (...a) => postMessage({ t: "log",  d: a.map(v => typeof v === "object" ? JSON.stringify(v) : String(v)).join(" ") });
      const _warn  = (...a) => postMessage({ t: "log",  d: a.map(String).join(" ") });
      const _error = (...a) => postMessage({ t: "err",  d: a.map(String).join(" ") });
      self.console = { log: _log, warn: _warn, error: _error, info: _log, debug: _log };
      try {
        const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
        new AsyncFunction(${JSON.stringify(code)})().then(() => postMessage({ t: "done" })).catch(e => {
          postMessage({ t: "err", d: String(e) });
          postMessage({ t: "done" });
        });
      } catch(e) {
        postMessage({ t: "err", d: String(e) });
        postMessage({ t: "done" });
      }
    `
    const blob = new Blob([workerSrc], { type: "application/javascript" })
    const url = URL.createObjectURL(blob)
    const worker = new Worker(url)

    const finish = () => {
      worker.terminate()
      URL.revokeObjectURL(url)
      resolve({ stdout: logs.join("\n"), stderr: errs.join("\n") })
    }

    const timer = setTimeout(() => {
      errs.push("Execution timed out (10s)")
      finish()
    }, 10_000)

    worker.onmessage = ({ data }) => {
      if (data.t === "log")  logs.push(data.d)
      else if (data.t === "err")  errs.push(data.d)
      else if (data.t === "done") { clearTimeout(timer); finish() }
    }
    worker.onerror = (e) => {
      errs.push(e.message ?? "Unknown error")
      clearTimeout(timer)
      finish()
    }
  })
}

// ── Python: run via Pyodide (WebAssembly, loaded once from CDN) ───────────────

let pyodideReady: Promise<any> | null = null

function getPyodide(): Promise<any> {
  if (pyodideReady) return pyodideReady
  pyodideReady = new Promise((resolve, reject) => {
    if ((window as any).loadPyodide) {
      ;(window as any).loadPyodide().then(resolve).catch(reject)
      return
    }
    const script = document.createElement("script")
    script.src = "https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js"
    script.onload = () => (window as any).loadPyodide().then(resolve).catch(reject)
    script.onerror = () => reject(new Error("Failed to load Python runtime"))
    document.head.appendChild(script)
  })
  return pyodideReady
}

async function runPython(code: string): Promise<ExecutionResult> {
  const pyodide = await getPyodide()
  const stdout: string[] = []
  const stderr: string[] = []

  pyodide.setStdout({ batched: (s: string) => stdout.push(s) })
  pyodide.setStderr({ batched: (s: string) => stderr.push(s) })

  try {
    await pyodide.runPythonAsync(code)
  } catch (e: any) {
    stderr.push(e.message ?? String(e))
  }

  return { stdout: stdout.join("\n"), stderr: stderr.join("\n") }
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function executeCode(language: string, code: string): Promise<ExecutionResult> {
  const lang = language?.toLowerCase()
  if (lang === "python") return runPython(code)
  if (lang === "javascript" || lang === "js") return runJavaScript(code)
  throw new Error(`Language "${language}" is not runnable in the browser`)
}
