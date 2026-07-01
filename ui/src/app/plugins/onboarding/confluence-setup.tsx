import { useEffect, useState } from "react"
import {
    Loader2, Plug, CheckCircle2, Check, FileSearch, AlertTriangle, Sparkles,
    RefreshCw, Search,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import {
    Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { getRequest, postRequest, patchRequest } from "@/services"
import { toast } from "@/hooks/use-toast"

type Status = {
    connected: boolean
    status: string | null
    site_url: string | null
    space_count: number
    doc_count: number
}
type Gap = { space_key: string; name: string | null; likely_docs: number }
type Space = { key: string; name: string; id: string; suggested: boolean }
type Candidate = {
    id: number
    page_id: string
    title: string
    space_key: string | null
    role_tags: string[]
    confidence: number | null
}
type WizardStep = "spaces" | "ingesting" | "reviewing"

function CheckRow({
    checked, onToggle, children,
}: { checked: boolean; onToggle: () => void; children: React.ReactNode }) {
    return (
        <button
            type="button"
            onClick={onToggle}
            className={cn(
                "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors",
                checked ? "border-primary/60 bg-primary/5" : "border-border hover:border-primary/40"
            )}
        >
            <span
                className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                    checked ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
                )}
            >
                {checked && <Check className="h-3 w-3" />}
            </span>
            <span className="min-w-0 flex-1">{children}</span>
        </button>
    )
}

export function ConfluenceSetup() {
    const [status, setStatus] = useState<Status | null>(null)
    const [loading, setLoading] = useState(true)
    const [connecting, setConnecting] = useState(false)

    const [open, setOpen] = useState(false)
    const [step, setStep] = useState<WizardStep>("spaces")

    const [spaces, setSpaces] = useState<Space[]>([])
    const [spacesLoading, setSpacesLoading] = useState(false)
    const [selectedSpaces, setSelectedSpaces] = useState<Set<string>>(new Set())
    const [starting, setStarting] = useState(false)

    const [jobId, setJobId] = useState<number | null>(null)
    const [progress, setProgress] = useState<{ total: number; processed: number; status: string }>({
        total: 0, processed: 0, status: "running",
    })

    const [candidates, setCandidates] = useState<Candidate[]>([])
    const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set())
    const [confirming, setConfirming] = useState(false)

    const [gaps, setGaps] = useState<Gap[] | null>(null)
    const [gapsLoading, setGapsLoading] = useState(false)
    const [reconciling, setReconciling] = useState(false)

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

    async function openWizard(preselect?: string[]) {
        setOpen(true)
        setStep("spaces")
        setSpaces([])
        setSpacesLoading(true)
        const { success, data } = await getRequest("/py/confluence/spaces")
        setSpacesLoading(false)
        if (success) {
            const list: Space[] = data.spaces || []
            setSpaces(list)
            const preset = preselect && preselect.length
                ? preselect
                : list.filter(s => s.suggested).map(s => s.key)
            setSelectedSpaces(new Set(preset))
        }
    }

    async function findGaps() {
        setGapsLoading(true)
        const { success, data } = await getRequest("/py/confluence/gaps")
        setGapsLoading(false)
        if (success) {
            setGaps(data.gaps || [])
            if (!data.gaps?.length) {
                toast({ title: "No gaps found", description: "Every space with onboarding docs is already connected." })
            }
        }
    }

    async function runReconcile() {
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

    function toggle(set: Set<string>, key: string): Set<string> {
        const next = new Set(set)
        next.has(key) ? next.delete(key) : next.add(key)
        return next
    }

    async function startIngest() {
        const keys = Array.from(selectedSpaces)
        if (!keys.length) return
        setStarting(true)
        const { success, data } = await postRequest("/py/confluence/ingest", { space_keys: keys })
        setStarting(false)
        if (success && data?.job_id != null) {
            setJobId(data.job_id)
            setProgress({ total: 0, processed: 0, status: "running" })
            setStep("ingesting")
        }
    }

    // Poll the ingestion job while on the ingesting step.
    useEffect(() => {
        if (step !== "ingesting" || jobId == null) return
        let active = true
        const tick = async () => {
            const { success, data } = await getRequest(`/py/confluence/ingest/${jobId}`)
            if (!active || !success) return
            setProgress({ total: data.total_pages, processed: data.processed_pages, status: data.status })
            if (data.status === "done") { active = false; loadCandidates() }
            else if (data.status === "failed") { active = false }
        }
        tick()
        const id = window.setInterval(tick, 1500)
        return () => { active = false; window.clearInterval(id) }
    }, [step, jobId])

    async function loadCandidates() {
        const { success, data } = await getRequest("/py/confluence/candidates")
        if (success) {
            const list: Candidate[] = data.candidates || []
            setCandidates(list)
            setSelectedDocs(new Set(list.map(c => c.page_id)))
            setStep("reviewing")
        }
    }

    async function confirmDocs() {
        const ids = Array.from(selectedDocs)
        if (!ids.length) return
        setConfirming(true)
        const { success } = await patchRequest("/py/confluence/candidates", { page_ids: ids })
        setConfirming(false)
        if (success) {
            setOpen(false)
            loadStatus()
        }
    }

    const pct = progress.total > 0 ? Math.round((progress.processed / progress.total) * 100) : 0

    if (loading) return <Skeleton className="h-14 w-full rounded-xl" />

    return (
        <>
            {status?.connected ? (
                <div className="space-y-2">
                    <div className={cn(
                        "flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3",
                        status.doc_count > 0 ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50/50"
                    )}>
                        <div className="flex items-center gap-2.5 min-w-0">
                            {status.doc_count > 0
                                ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                                : <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />}
                            <div className="min-w-0">
                                <p className="text-sm font-medium leading-tight">
                                    {status.doc_count > 0
                                        ? `Confluence connected · ${status.doc_count} document${status.doc_count === 1 ? "" : "s"} ready`
                                        : "Confluence connected · no documents yet"}
                                </p>
                                <p className="truncate text-xs text-muted-foreground">
                                    {status.doc_count > 0
                                        ? `${status.site_url || "Your workspace"} · ${status.space_count} space${status.space_count === 1 ? "" : "s"}`
                                        : "Ingest docs to enable onboarding generation."}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <Button variant="ghost" size="sm" onClick={runReconcile} disabled={reconciling} title="Sync with Confluence">
                                <RefreshCw className={cn("h-4 w-4", reconciling && "animate-spin")} />
                            </Button>
                            <Button variant="outline" size="sm" onClick={findGaps} disabled={gapsLoading}>
                                {gapsLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
                                Find missing
                            </Button>
                            <Button variant={status.doc_count > 0 ? "outline" : "default"} size="sm" onClick={() => openWizard()}>
                                <FileSearch className="mr-2 h-4 w-4" />Ingest docs
                            </Button>
                        </div>
                    </div>

                    {gaps && gaps.length > 0 && (
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-200 bg-indigo-50/50 px-4 py-2.5">
                            <p className="text-sm text-indigo-900">
                                Found <span className="font-semibold">{gaps.reduce((n, g) => n + g.likely_docs, 0)}</span> likely docs in unconnected spaces:{" "}
                                <span className="text-muted-foreground">{gaps.map(g => g.name || g.space_key).join(", ")}</span>
                            </p>
                            <Button size="sm" onClick={() => { setGaps(null); openWizard(gaps.map(g => g.space_key)) }}>
                                Add these
                            </Button>
                        </div>
                    )}
                </div>
            ) : (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
                    <div className="flex items-center gap-2.5 min-w-0">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                            <Plug className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                            <p className="text-sm font-medium leading-tight">Connect your Confluence</p>
                            <p className="text-xs text-muted-foreground">Generate onboarding from your company's real docs.</p>
                        </div>
                    </div>
                    <Button size="sm" onClick={handleConnect} disabled={connecting}>
                        {connecting
                            ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Connecting…</>
                            : <><Plug className="mr-2 h-4 w-4" />Connect Confluence</>}
                    </Button>
                </div>
            )}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-lg">
                    {step === "spaces" && (
                        <>
                            <DialogHeader>
                                <DialogTitle>Select spaces to ingest</DialogTitle>
                                <DialogDescription>
                                    We pre-selected spaces that look like engineering docs. Adjust as needed.
                                </DialogDescription>
                            </DialogHeader>
                            <div className="max-h-[50vh] space-y-1.5 overflow-y-auto py-1">
                                {spacesLoading ? (
                                    [...Array(4)].map((_, i) => <Skeleton key={i} className="h-11 w-full rounded-lg" />)
                                ) : spaces.length === 0 ? (
                                    <p className="py-6 text-center text-sm text-muted-foreground">No spaces found.</p>
                                ) : (
                                    spaces.map(s => (
                                        <CheckRow
                                            key={s.key}
                                            checked={selectedSpaces.has(s.key)}
                                            onToggle={() => setSelectedSpaces(prev => toggle(prev, s.key))}
                                        >
                                            <span className="flex items-center gap-2">
                                                <span className="truncate text-sm font-medium">{s.name}</span>
                                                <span className="text-xs text-muted-foreground">{s.key}</span>
                                                {s.suggested && (
                                                    <Badge variant="outline" className="ml-auto shrink-0 border-primary/30 text-primary text-[10px]">
                                                        <Sparkles className="mr-1 h-3 w-3" />suggested
                                                    </Badge>
                                                )}
                                            </span>
                                        </CheckRow>
                                    ))
                                )}
                            </div>
                            <DialogFooter className="gap-2">
                                <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                                <Button onClick={startIngest} disabled={starting || selectedSpaces.size === 0}>
                                    {starting
                                        ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Starting…</>
                                        : <>Ingest {selectedSpaces.size} space{selectedSpaces.size === 1 ? "" : "s"}</>}
                                </Button>
                            </DialogFooter>
                        </>
                    )}

                    {step === "ingesting" && (
                        <>
                            <DialogHeader>
                                <DialogTitle>
                                    {progress.status === "failed" ? "Ingestion failed" : "Reading your docs…"}
                                </DialogTitle>
                                <DialogDescription>
                                    {progress.status === "failed"
                                        ? "Something went wrong. You can try again."
                                        : "We're scanning pages and classifying which are useful for onboarding."}
                                </DialogDescription>
                            </DialogHeader>
                            <div className="py-4">
                                {progress.status === "failed" ? (
                                    <div className="flex items-center gap-2 text-sm text-destructive">
                                        <AlertTriangle className="h-4 w-4" /> Ingestion job failed.
                                    </div>
                                ) : (
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                            {progress.total > 0
                                                ? `Processed ${progress.processed} of ${progress.total} pages`
                                                : "Finding pages…"}
                                        </div>
                                        <Progress value={pct} className="h-2" />
                                    </div>
                                )}
                            </div>
                            <DialogFooter className="gap-2">
                                {progress.status === "failed" && (
                                    <Button variant="outline" onClick={() => setStep("spaces")}>Back</Button>
                                )}
                            </DialogFooter>
                        </>
                    )}

                    {step === "reviewing" && (
                        <>
                            <DialogHeader>
                                <DialogTitle>Review documents</DialogTitle>
                                <DialogDescription>
                                    {candidates.length} document{candidates.length === 1 ? "" : "s"} look relevant. Confirm the ones to include.
                                </DialogDescription>
                            </DialogHeader>
                            <div className="max-h-[50vh] space-y-1.5 overflow-y-auto py-1">
                                {candidates.length === 0 ? (
                                    <p className="py-6 text-center text-sm text-muted-foreground">
                                        No new relevant documents were found.
                                    </p>
                                ) : (
                                    candidates.map(c => (
                                        <CheckRow
                                            key={c.page_id}
                                            checked={selectedDocs.has(c.page_id)}
                                            onToggle={() => setSelectedDocs(prev => toggle(prev, c.page_id))}
                                        >
                                            <span className="block truncate text-sm font-medium">{c.title}</span>
                                            <span className="mt-0.5 flex flex-wrap items-center gap-1.5">
                                                {c.space_key && <span className="text-xs text-muted-foreground">{c.space_key}</span>}
                                                {c.role_tags.map(t => (
                                                    <Badge key={t} variant="outline" className="text-[10px]">{t}</Badge>
                                                ))}
                                                {c.confidence != null && (
                                                    <span className="ml-auto text-[10px] text-muted-foreground">
                                                        {Math.round(c.confidence * 100)}% match
                                                    </span>
                                                )}
                                            </span>
                                        </CheckRow>
                                    ))
                                )}
                            </div>
                            <DialogFooter className="gap-2">
                                <Button variant="outline" onClick={() => setOpen(false)}>Close</Button>
                                <Button onClick={confirmDocs} disabled={confirming || selectedDocs.size === 0}>
                                    {confirming
                                        ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving…</>
                                        : <>Confirm {selectedDocs.size}</>}
                                </Button>
                            </DialogFooter>
                        </>
                    )}
                </DialogContent>
            </Dialog>
        </>
    )
}
