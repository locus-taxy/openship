import { useEffect, useState } from "react"
import {
    Loader2, Plug, CheckCircle2, AlertTriangle, RefreshCw, DownloadCloud, Info, FileText, ListChecks, Ban,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { getRequest, postRequest } from "@/services"
import { toast } from "@/hooks/use-toast"
import useStore from "@/store"

type Source = "confluence" | "jira"

type JobProgress = {
    status: string
    kind?: string
    source?: Source
    phase: string | null
    total_spaces: number
    processed_spaces: number
    total_pages: number
    processed_pages: number
    total_chunks: number
    embedded_chunks: number
    error?: string | null
}
type JobResult = JobProgress & { job_id: number }
type SourceCounts = { page_count: number; chunk_count: number }
type Status = {
    connected: boolean
    status: string | null
    site_url: string | null
    sources: Record<Source, SourceCounts>
    ingest: JobResult | null
    last_result?: JobResult | null
}

// Per-source display copy. Confluence = pages/spaces; Jira = issues/projects.
const SOURCE_META: Record<Source, {
    name: string
    icon: typeof FileText
    unit: string
    container: string
    blurb: string
    accent: string
}> = {
    confluence: {
        name: "Confluence",
        icon: FileText,
        unit: "docs",
        container: "spaces",
        blurb: "Pages power onboarding plans and knowledge answers.",
        accent: "from-sky-500 to-blue-600",
    },
    jira: {
        name: "Jira",
        icon: ListChecks,
        unit: "issues",
        container: "projects",
        blurb: "Issues enrich knowledge answers (not used for onboarding).",
        accent: "from-indigo-500 to-violet-600",
    },
}

function announceJob(job: JobResult): { title: string; description: string; variant?: "destructive" } {
    const label = job.source ? SOURCE_META[job.source].name : "Atlassian"
    const isReconcile = job.kind === "reconcile"
    if (job.status === "cancelled") {
        return { title: `${label} sync cancelled`, description: job.error || "Stopped." }
    }
    if (job.status === "failed") {
        return {
            title: isReconcile ? `${label} sync failed` : `${label} ingestion failed`,
            description: job.error || "Something went wrong.",
            variant: "destructive",
        }
    }
    return {
        title: isReconcile ? `Synced with ${label}` : `${label} indexed`,
        description: job.error || (isReconcile ? "Done." : "Your knowledge base is up to date."),
    }
}

function formatElapsed(totalSeconds: number): string {
    const h = Math.floor(totalSeconds / 3600)
    const m = Math.floor((totalSeconds % 3600) / 60)
    const s = totalSeconds % 60
    const mm = String(m).padStart(2, "0")
    const ss = String(s).padStart(2, "0")
    return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

export default function ConnectionsPage() {
    const [status, setStatus] = useState<Status | null>(null)
    const [loading, setLoading] = useState(true)
    const [connecting, setConnecting] = useState(false)
    const [jobId, setJobId] = useState<number | null>(null)
    const [progress, setProgress] = useState<JobProgress | null>(null)
    const [elapsed, setElapsed] = useState(0)
    const [cancelling, setCancelling] = useState(false)
    const { setPluginName } = useStore((state: any) => state)

    useEffect(() => { setPluginName("Connections") }, [setPluginName])

    async function loadStatus() {
        const { success, data } = await getRequest("/py/connections/status")
        if (success) {
            setStatus(data)
            if (data.ingest) {
                setJobId(data.ingest.job_id)
                setProgress(data.ingest)
            } else if (data.last_result) {
                const key = "last_job_ack"
                if (window.localStorage.getItem(key) !== String(data.last_result.job_id)) {
                    window.localStorage.setItem(key, String(data.last_result.job_id))
                    toast(announceJob(data.last_result))
                }
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

    function optimisticProgress(source: Source): JobProgress {
        return {
            status: "running", kind: "ingest", source, phase: "reading",
            total_spaces: 0, processed_spaces: 0,
            total_pages: 0, processed_pages: 0, total_chunks: 0, embedded_chunks: 0,
        }
    }

    // A single "Sync" runs a full ingest: it adds new content, updates changed
    // content, AND drops anything removed upstream — one read, no separate reconcile.
    async function startIngest(source: Source) {
        setCancelling(false)
        const { success, data } = await postRequest(`/py/confluence/ingest?source=${source}`, {})
        if (success && data?.job_id != null) {
            setJobId(data.job_id)
            setProgress(optimisticProgress(source))
        } else {
            loadStatus()
        }
    }

    async function cancelJob() {
        if (jobId == null) return
        setCancelling(true)
        // Cooperative: the backend flips the job to 'cancelled'; the next poll reflects it.
        await postRequest(`/py/confluence/ingest/${jobId}/cancel`, {})
    }

    // Poll the running job (company-wide, so any source's job surfaces here).
    useEffect(() => {
        if (jobId == null || progress?.status !== "running") return
        let active = true
        const tick = async () => {
            const { success, data } = await getRequest(`/py/confluence/ingest/${jobId}`)
            if (!active || !success) return
            setProgress(data)
            if (data.status === "done" || data.status === "failed" || data.status === "cancelled") {
                active = false
                setCancelling(false)
                window.localStorage.removeItem(`ingest_started_${jobId}`)
                loadStatus()
            }
        }
        tick()
        const id = window.setInterval(tick, 2000)
        return () => { active = false; window.clearInterval(id) }
    }, [jobId, progress?.status])

    // Live elapsed timer, anchored per-job so it survives a refresh.
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

    if (loading) {
        return (
            <div className="p-4 sm:p-6 space-y-4">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-20 w-full rounded-xl" />
                <Skeleton className="h-32 w-full rounded-xl" />
            </div>
        )
    }

    const jobRunning = jobId != null && progress != null && progress.status === "running"
    const activeSource = progress?.source

    return (
        <div className="p-4 sm:p-6 space-y-6 max-w-3xl">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Connections</h1>
                <p className="text-muted-foreground text-sm mt-0.5">
                    Connect your Atlassian workspace and index Confluence &amp; Jira into your knowledge base.
                </p>
            </div>

            {/* Shared Atlassian connection */}
            <AtlassianCard status={status} connecting={connecting} onConnect={handleConnect} />

            {status?.connected && (
                <div className="space-y-3">
                    {(Object.keys(SOURCE_META) as Source[]).map((source) => (
                        <SourceCard
                            key={source}
                            source={source}
                            counts={status.sources?.[source] || { page_count: 0, chunk_count: 0 }}
                            busy={jobRunning}
                            progress={jobRunning && activeSource === source ? progress : null}
                            elapsed={elapsed}
                            cancelling={cancelling}
                            onIngest={() => startIngest(source)}
                            onCancel={cancelJob}
                            onDismiss={() => { setJobId(null); setProgress(null); setCancelling(false) }}
                        />
                    ))}
                    <p className="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
                        <Info className="h-3.5 w-3.5 shrink-0" />
                        Ingestion embeds your content locally — no API key or quota needed.
                    </p>
                </div>
            )}
        </div>
    )
}

function AtlassianCard({ status, connecting, onConnect }: {
    status: Status | null
    connecting: boolean
    onConnect: () => void
}) {
    const connected = !!status?.connected
    const needsReconnect = !connected && !!status?.status && status.status !== "ready"
    return (
        <div className={cn(
            "flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3.5",
            connected ? "border-emerald-200 bg-emerald-50/50"
                : needsReconnect ? "border-amber-200 bg-amber-50/50" : "border-border bg-card",
        )}>
            <div className="flex items-center gap-3 min-w-0">
                <div className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                    connected ? "bg-emerald-500/10 text-emerald-600"
                        : needsReconnect ? "bg-amber-100 text-amber-700" : "bg-primary/10 text-primary",
                )}>
                    {connected ? <CheckCircle2 className="h-5 w-5" />
                        : needsReconnect ? <AlertTriangle className="h-5 w-5" /> : <Plug className="h-5 w-5" />}
                </div>
                <div className="min-w-0">
                    <p className="text-sm font-semibold leading-tight">
                        {connected ? "Atlassian connected"
                            : needsReconnect ? "Atlassian connection expired" : "Connect Atlassian"}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                        {connected ? (status?.site_url || "Confluence & Jira available")
                            : needsReconnect ? "Your access needs renewing to keep indexing."
                                : "One connection grants both Confluence and Jira."}
                    </p>
                </div>
            </div>
            <Button size="sm" onClick={onConnect} disabled={connecting}
                variant={connected || needsReconnect ? "outline" : "default"}>
                {connecting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Connecting…</>
                    : connected ? <><RefreshCw className="mr-2 h-4 w-4" />Reconnect</>
                        : needsReconnect ? <><RefreshCw className="mr-2 h-4 w-4" />Reconnect</>
                            : <><Plug className="mr-2 h-4 w-4" />Connect</>}
            </Button>
        </div>
    )
}

function SourceCard({ source, counts, busy, progress, elapsed, cancelling, onIngest, onCancel, onDismiss }: {
    source: Source
    counts: SourceCounts
    busy: boolean
    progress: JobProgress | null
    elapsed: number
    cancelling: boolean
    onIngest: () => void
    onCancel: () => void
    onDismiss: () => void
}) {
    const meta = SOURCE_META[source]
    const Icon = meta.icon
    const hasDocs = counts.chunk_count > 0

    return (
        <div className="rounded-xl border border-border bg-card px-4 py-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                    <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-white", meta.accent)}>
                        <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                        <p className="text-sm font-semibold leading-tight">{meta.name}</p>
                        <p className="text-xs text-muted-foreground">
                            {hasDocs
                                ? `${counts.page_count} ${meta.unit} · ${counts.chunk_count} chunks indexed`
                                : meta.blurb}
                        </p>
                    </div>
                </div>
                {!progress && (
                    <div className="flex items-center gap-1.5">
                        <Button variant={hasDocs ? "outline" : "default"} size="sm" onClick={onIngest} disabled={busy} title={hasDocs ? `Sync ${meta.name}` : undefined}>
                            {hasDocs ? <RefreshCw className="mr-2 h-4 w-4" /> : <DownloadCloud className="mr-2 h-4 w-4" />}
                            {hasDocs ? `Sync` : `Ingest ${meta.unit}`}
                        </Button>
                    </div>
                )}
            </div>

            {progress && <JobProgressView source={source} progress={progress} elapsed={elapsed} cancelling={cancelling} onCancel={onCancel} onDismiss={onDismiss} />}
        </div>
    )
}

function JobProgressView({ source, progress, elapsed, cancelling, onCancel, onDismiss }: {
    source: Source
    progress: JobProgress
    elapsed: number
    cancelling: boolean
    onCancel: () => void
    onDismiss: () => void
}) {
    const meta = SOURCE_META[source]
    const failed = progress.status === "failed"
    const cancelled = progress.status === "cancelled"
    const isReconcile = progress.kind === "reconcile"
    const pct = (done: number, total: number) => (total > 0 ? Math.round((done / total) * 100) : 0)
    const STAGES = isReconcile
        ? [
            { key: "reading", label: `Reading ${meta.container}`, done: progress.processed_spaces, total: progress.total_spaces },
            { key: "reconciling", label: "Applying changes", done: 0, total: 0 },
        ]
        : [
            { key: "reading", label: `Reading ${meta.container}`, done: progress.processed_spaces, total: progress.total_spaces },
            { key: "indexing", label: `Scanning ${meta.unit}`, done: progress.processed_pages, total: progress.total_pages },
            { key: "embedding", label: "Embedding chunks", done: progress.embedded_chunks, total: progress.total_chunks },
        ]
    const order = isReconcile ? ["reading", "reconciling", "done"] : ["reading", "indexing", "embedding", "done"]
    const currentIdx = Math.max(0, order.indexOf(progress.phase || "reading"))

    if (failed) {
        return (
            <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertTriangle className="h-4 w-4" /> {isReconcile ? "Sync" : "Ingestion"} failed after {formatElapsed(elapsed)}.
                <Button variant="outline" size="sm" className="ml-auto" onClick={onDismiss}>Dismiss</Button>
            </div>
        )
    }
    if (cancelled) {
        return (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Ban className="h-4 w-4" /> Cancelled after {formatElapsed(elapsed)}. Partial progress saved.
                <Button variant="outline" size="sm" className="ml-auto" onClick={onDismiss}>Dismiss</Button>
            </div>
        )
    }
    return (
        <div className="space-y-3 border-t border-border pt-3">
            <div className="flex items-center gap-2 text-sm font-medium">
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
                {isReconcile ? `Syncing with ${meta.name}…` : `Indexing ${meta.name}…`}
                <span className="ml-auto text-xs font-normal tabular-nums text-muted-foreground">{formatElapsed(elapsed)}</span>
                <Button variant="ghost" size="sm" className="h-7 px-2 text-muted-foreground hover:text-destructive" onClick={onCancel} disabled={cancelling}>
                    <Ban className="mr-1 h-3.5 w-3.5" />{cancelling ? "Cancelling…" : "Cancel"}
                </Button>
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
        </div>
    )
}
