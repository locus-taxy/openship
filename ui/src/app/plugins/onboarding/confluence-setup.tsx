import { useEffect, useState } from "react"
import { Loader2, Plug, CheckCircle2, AlertTriangle, RefreshCw, DownloadCloud } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { getRequest, postRequest } from "@/services"
import { toast } from "@/hooks/use-toast"

type Status = {
    connected: boolean
    status: string | null
    site_url: string | null
    page_count: number
    chunk_count: number
}
type JobProgress = {
    status: string
    total_pages: number
    processed_pages: number
    total_chunks: number
    embedded_chunks: number
}

export function ConfluenceSetup() {
    const [status, setStatus] = useState<Status | null>(null)
    const [loading, setLoading] = useState(true)
    const [connecting, setConnecting] = useState(false)
    const [reconciling, setReconciling] = useState(false)
    const [jobId, setJobId] = useState<number | null>(null)
    const [progress, setProgress] = useState<JobProgress | null>(null)

    async function loadStatus() {
        const { success, data } = await getRequest("/py/confluence/status")
        if (success) setStatus(data)
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
            setProgress({ status: "running", total_pages: 0, processed_pages: 0, total_chunks: 0, embedded_chunks: 0 })
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
                if (data.status === "done") loadStatus()
            }
        }
        tick()
        const id = window.setInterval(tick, 2000)
        return () => { active = false; window.clearInterval(id) }
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

    // Active ingestion — show progress.
    if (jobId != null && progress && progress.status !== "done") {
        const pagePct = progress.total_pages > 0 ? Math.round((progress.processed_pages / progress.total_pages) * 100) : 0
        const chunkPct = progress.total_chunks > 0 ? Math.round((progress.embedded_chunks / progress.total_chunks) * 100) : 0
        const failed = progress.status === "failed"
        return (
            <div className="rounded-xl border border-border bg-card px-4 py-4 space-y-3">
                {failed ? (
                    <div className="flex items-center gap-2 text-sm text-destructive">
                        <AlertTriangle className="h-4 w-4" /> Ingestion failed.
                        <Button variant="outline" size="sm" className="ml-auto" onClick={() => { setJobId(null); setProgress(null) }}>Dismiss</Button>
                    </div>
                ) : (
                    <>
                        <div className="flex items-center gap-2 text-sm font-medium">
                            <Loader2 className="h-4 w-4 animate-spin text-primary" />
                            {progress.total_chunks > 0 ? "Embedding documents…" : "Reading pages…"}
                        </div>
                        <div className="space-y-1">
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>Pages</span><span>{progress.processed_pages} / {progress.total_pages}</span>
                            </div>
                            <Progress value={pagePct} className="h-1.5" />
                        </div>
                        {progress.total_chunks > 0 && (
                            <div className="space-y-1">
                                <div className="flex justify-between text-xs text-muted-foreground">
                                    <span>Chunks embedded</span><span>{progress.embedded_chunks} / {progress.total_chunks}</span>
                                </div>
                                <Progress value={chunkPct} className="h-1.5" />
                            </div>
                        )}
                    </>
                )}
            </div>
        )
    }

    if (!status?.connected) {
        return (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                <div className="flex items-center gap-2.5 min-w-0">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <Plug className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                        <p className="text-sm font-medium leading-tight">Connect your Confluence</p>
                        <p className="text-xs text-muted-foreground">Index your company's docs to power onboarding and answers.</p>
                    </div>
                </div>
                <Button size="sm" onClick={handleConnect} disabled={connecting}>
                    {connecting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Connecting…</> : <><Plug className="mr-2 h-4 w-4" />Connect Confluence</>}
                </Button>
            </div>
        )
    }

    const hasDocs = status.chunk_count > 0
    return (
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
    )
}
