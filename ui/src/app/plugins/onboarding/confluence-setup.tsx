import { useEffect, useState } from "react"
import { Loader2, Plug, CheckCircle2, AlertTriangle, RefreshCw, DownloadCloud, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { getRequest, postRequest } from "@/services"
import { toast } from "@/hooks/use-toast"

type JobProgress = {
    status: string
    phase: string | null
    total_spaces: number
    processed_spaces: number
    total_pages: number
    processed_pages: number
    total_chunks: number
    embedded_chunks: number
}
type Status = {
    connected: boolean
    status: string | null
    site_url: string | null
    page_count: number
    chunk_count: number
    ingest: (JobProgress & { job_id: number }) | null
}

// mm:ss (or h:mm:ss past an hour) for the live ingest timer.
function formatElapsed(totalSeconds: number): string {
    const h = Math.floor(totalSeconds / 3600)
    const m = Math.floor((totalSeconds % 3600) / 60)
    const s = totalSeconds % 60
    const mm = String(m).padStart(2, "0")
    const ss = String(s).padStart(2, "0")
    return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

export function ConfluenceSetup({ onStatus }: { onStatus?: (s: Status) => void } = {}) {
    const [status, setStatus] = useState<Status | null>(null)
    const [loading, setLoading] = useState(true)
    const [connecting, setConnecting] = useState(false)
    const [reconciling, setReconciling] = useState(false)
    const [jobId, setJobId] = useState<number | null>(null)
    const [progress, setProgress] = useState<JobProgress | null>(null)
    const [elapsed, setElapsed] = useState(0)

    async function loadStatus() {
        const { success, data } = await getRequest("/py/confluence/status")
        if (success) {
            setStatus(data)
            onStatus?.(data)
            // Resume the live progress view if an ingest is already running for the
            // company (e.g. after a page refresh, or a teammate started it).
            if (data.ingest) {
                setJobId(data.ingest.job_id)
                setProgress(data.ingest)
            }
        }
        setLoading(false)
    }

    useEffect(() => { loadStatus() }, [])

    async function handleConnect() {
        setConnecting(true)
        const { success, data } = await postRequest("/py/confluence/connect", {})
        setConnecting(false)
        if (success && data?.authorize_url) window.location.href = data.authorize_url
    }

    async function startIngest() {
        const { success, data } = await postRequest("/py/confluence/ingest", {})
        if (success && data?.job_id != null) {
            setJobId(data.job_id)
            setProgress({
                status: "running", phase: "reading",
                total_spaces: 0, processed_spaces: 0,
                total_pages: 0, processed_pages: 0, total_chunks: 0, embedded_chunks: 0,
            })
        } else {
            // Ingest can 409 if the connection has expired since the page loaded.
            // Re-fetch status so the "Reconnect" state surfaces instead of a stale card.
            loadStatus()
        }
    }

    // Poll the ingestion job while it runs.
    useEffect(() => {
        if (jobId == null || progress?.status !== "running") return
        let active = true
        const tick = async () => {
            const { success, data } = await getRequest(`/py/confluence/ingest/${jobId}`)
            if (!active || !success) return
            setProgress(data)
            if (data.status === "done" || data.status === "failed") {
                active = false
                window.localStorage.removeItem(`ingest_started_${jobId}`)
                if (data.status === "done") loadStatus()
            }
        }
        tick()
        const id = window.setInterval(tick, 2000)
        return () => { active = false; window.clearInterval(id) }
    }, [jobId, progress?.status])

    // Live elapsed timer, anchored per-job in localStorage so it survives a refresh.
    useEffect(() => {
        if (jobId == null || progress?.status !== "running") return
        const key = `ingest_started_${jobId}`
        let start = Number(window.localStorage.getItem(key))
        if (!start) { start = Date.now(); window.localStorage.setItem(key, String(start)) }
        const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)))
        tick()
        const id = window.setInterval(tick, 1000)
        return () => window.clearInterval(id)
    }, [jobId, progress?.status])

    async function handleReconcile() {
        setReconciling(true)
        const { success, data } = await postRequest("/py/confluence/reconcile", {})
        setReconciling(false)
        if (success) {
            toast({
                title: "Synced with Confluence",
                description: `${data.deactivated} removed, ${data.reactivated} restored.`,
            })
            loadStatus()
        }
    }

    if (loading) return <Skeleton className="h-14 w-full rounded-xl" />

    // Active ingestion — show staged progress (reading → indexing → embedding).
    if (jobId != null && progress && progress.status !== "done") {
        const failed = progress.status === "failed"
        const pct = (done: number, total: number) => (total > 0 ? Math.round((done / total) * 100) : 0)
        const STAGES = [
            { key: "reading", label: "Reading spaces", done: progress.processed_spaces, total: progress.total_spaces },
            { key: "indexing", label: "Scanning pages", done: progress.processed_pages, total: progress.total_pages },
            { key: "embedding", label: "Embedding chunks", done: progress.embedded_chunks, total: progress.total_chunks },
        ]
        const order = ["reading", "indexing", "embedding", "done"]
        const currentIdx = order.indexOf(progress.phase || "reading")
        return (
            <div className="rounded-xl border border-border bg-card px-4 py-4 space-y-3">
                {failed ? (
                    <div className="flex items-center gap-2 text-sm text-destructive">
                        <AlertTriangle className="h-4 w-4" /> Ingestion failed after {formatElapsed(elapsed)}.
                        <Button variant="outline" size="sm" className="ml-auto" onClick={() => { setJobId(null); setProgress(null) }}>Dismiss</Button>
                    </div>
                ) : (
                    <>
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <Loader2 className="h-4 w-4 animate-spin text-primary" />
                            Indexing your Confluence…
                            <span className="ml-auto text-xs font-normal tabular-nums text-muted-foreground">{formatElapsed(elapsed)}</span>
                        </div>
                        {STAGES.map((stage, idx) => {
                            const isDone = idx < currentIdx
                            const isActive = idx === currentIdx
                            const value = isDone ? 100 : pct(stage.done, stage.total)
                            return (
                                <div key={stage.key} className={cn("space-y-1", !isActive && !isDone && "opacity-50")}>
                                    <div className="flex justify-between text-xs text-muted-foreground">
                                        <span className="flex items-center gap-1.5">
                                            {isDone && <CheckCircle2 className="h-3 w-3 text-emerald-600" />}
                                            {stage.label}
                                        </span>
                                        <span>{isDone ? "done" : stage.total > 0 ? `${stage.done} / ${stage.total}` : "…"}</span>
                                    </div>
                                    <Progress value={value} className="h-1.5" />
                                </div>
                            )
                        })}
                    </>
                )}
            </div>
        )
    }

    // Reconcile is a full re-scan of every space — show a clear status while it runs.
    if (reconciling) {
        return (
            <div className="rounded-xl border border-border bg-card px-4 py-4 space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    Syncing with Confluence…
                </div>
                <p className="text-xs text-muted-foreground">
                    Re-scanning every space to detect pages that changed or were removed. This can
                    take a minute on large workspaces — you can keep working.
                </p>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
                </div>
            </div>
        )
    }

    if (!status?.connected) {
        // A connection row exists but isn't usable (token expired / refresh failed):
        // show a distinct "Reconnect" state rather than a generic first-time connect.
        const needsReconnect = !!status?.status && status.status !== "ready"
        return (
            <div className="space-y-1.5">
                <div className={cn(
                    "flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3",
                    needsReconnect ? "border-amber-200 bg-amber-50/50" : "border-border bg-card"
                )}>
                    <div className="flex items-center gap-2.5 min-w-0">
                        <div className={cn(
                            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                            needsReconnect ? "bg-amber-100 text-amber-700" : "bg-primary/10 text-primary"
                        )}>
                            {needsReconnect ? <AlertTriangle className="h-4 w-4" /> : <Plug className="h-4 w-4" />}
                        </div>
                        <div className="min-w-0">
                            <p className="text-sm font-medium leading-tight">
                                {needsReconnect ? "Confluence connection expired" : "Connect your Confluence"}
                            </p>
                            <p className="text-xs text-muted-foreground">
                                {needsReconnect
                                    ? "Your access needs renewing. Reconnect to keep your knowledge base up to date."
                                    : "Index your company's docs to power onboarding and answers."}
                            </p>
                        </div>
                    </div>
                    <Button size="sm" onClick={handleConnect} disabled={connecting} variant={needsReconnect ? "outline" : "default"}>
                        {connecting
                            ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Connecting…</>
                            : needsReconnect
                                ? <><RefreshCw className="mr-2 h-4 w-4" />Reconnect</>
                                : <><Plug className="mr-2 h-4 w-4" />Connect Confluence</>}
                    </Button>
                </div>
                {!needsReconnect && <IngestKeyNote />}
            </div>
        )
    }

    const hasDocs = status.chunk_count > 0
    return (
        <div className="space-y-1.5">
            <div className={cn(
                "flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3",
                hasDocs ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50/50"
            )}>
                <div className="flex items-center gap-2.5 min-w-0">
                    {hasDocs
                        ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                        : <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />}
                    <div className="min-w-0">
                        <p className="text-sm font-medium leading-tight">
                            {hasDocs
                                ? `Confluence connected · ${status.page_count} docs · ${status.chunk_count} chunks indexed`
                                : "Confluence connected · nothing indexed yet"}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                            {hasDocs ? (status.site_url || "Your workspace") : "Ingest your docs to enable onboarding and answers."}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-1.5">
                    {hasDocs && (
                        <Button variant="ghost" size="sm" onClick={handleReconcile} disabled={reconciling} title="Sync with Confluence">
                            <RefreshCw className={cn("h-4 w-4", reconciling && "animate-spin")} />
                        </Button>
                    )}
                    <Button variant={hasDocs ? "outline" : "default"} size="sm" onClick={startIngest}>
                        <DownloadCloud className="mr-2 h-4 w-4" />{hasDocs ? "Re-ingest" : "Ingest all docs"}
                    </Button>
                </div>
            </div>
            <IngestKeyNote />
        </div>
    )
}

// Embeddings run locally (fastembed), so ingestion needs no API key or quota.
// A Gemini key is still used for the Q&A answers, not for indexing.
function IngestKeyNote() {
    return (
        <p className="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
            <Info className="h-3.5 w-3.5 shrink-0" />
            Ingestion embeds your docs locally — no API key or quota needed.
        </p>
    )
}
