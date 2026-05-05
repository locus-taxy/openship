import { useEffect, useRef, useState } from "react"
import { LlmBar } from "@/components/llm-bar"
import { useParams, useNavigate, useSearchParams } from "react-router"
import {
    ArrowLeft, ArrowRight, CheckCircle2,
    FileText, ChevronDown, ChevronRight, Sparkles, Loader2,
    Globe, Copy, Check, PanelLeftClose, PanelLeftOpen, GraduationCap,
} from "lucide-react"
import { QuizPanel } from "./quiz"
import { Button } from "@/components/ui/button"
import {
    Dialog, DialogContent, DialogDescription, DialogFooter,
    DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { ToastAction } from "@/components/ui/toast"
import { useToast } from "@/hooks/use-toast"
import { Skeleton } from "@/components/ui/skeleton"
import { Progress } from "@/components/ui/progress"
import { getRequest, postRequest } from "@/services"
import api from "@/services"
import useStore from "@/store"
import { sanitizeHtml } from "@/lib/sanitize"
import { useSidebar } from "@/components/ui/sidebar"
import hljs from "highlight.js"
import "highlight.js/styles/atom-one-dark.css"

interface Chapter {
    id: number
    day: number
    topic: string
    task: string
    hours: number
    completed: boolean
    has_content: boolean
}

interface Week {
    week: number
    tasks: Chapter[]
}

interface Month {
    month: number
    weeks: Week[]
}

interface SyllabusDetail {
    skill_id: number
    skill: string
    days: number
    hours: number
    share_enabled: boolean
    quiz_difficulty: string
    quiz_status: string   // "not_generated" | "available" | "passed"
    created_at: string
    months: Month[]
}

// ─── Chapter Content Panel (right) ───────────────────────────────────────────

function ChapterContentPanel({ chapter, isGenerating, onGenerationStart, onGenerationEnd, onContentGenerated, onMarkComplete, onGoToNext, hasNext }: {
    chapter: Chapter
    isGenerating: boolean
    onGenerationStart: (taskId: number) => void
    onGenerationEnd: (taskId: number) => void
    onContentGenerated: (taskId: number) => void
    onMarkComplete: (taskId: number) => void
    onGoToNext: () => void
    hasNext: boolean
}) {
    const [content, setContent] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const generating = isGenerating
    // const [sending, setSending] = useState(false)
    const [completed, setCompleted] = useState(chapter.completed)
    // const [emailSent, setEmailSent] = useState(false)
    const [hasContent, setHasContent] = useState(chapter.has_content)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const proseRef = useRef<HTMLDivElement>(null)
    const { toast } = useToast()
    const { setSettingsOpen } = useStore((s: any) => s)

    useEffect(() => {
        setHasContent(chapter.has_content)
        setCompleted(chapter.completed)
        // setEmailSent(false)
        setContent(null)
        if (chapter.has_content) loadContent()
    }, [chapter.id])

    // Apply syntax highlighting, line numbers, and copy button to every <pre>
    useEffect(() => {
        const container = proseRef.current
        if (!container || !content) return

        container.querySelectorAll("pre").forEach((pre) => {
            if (pre.dataset.processed) return
            pre.dataset.processed = "true"

            const codeEl = pre.querySelector("code") as HTMLElement | null
            if (!codeEl) return

            // — Capture raw text before highlight (used for copy + line count) —
            const rawText = codeEl.innerText
            const lines = rawText.split("\n")
            if (lines[lines.length - 1] === "") lines.pop()
            const lineCount = lines.length

            // — Syntax highlight (operates on codeEl innerHTML, never split) —
            hljs.highlightElement(codeEl)

            // — Pre styles —
            Object.assign(pre.style, {
                position: "relative",
                borderRadius: "10px",
                padding: "0",
                overflow: "hidden",
                background: "transparent",
            })

            // — Flex container: gutter | scrollable code —
            const flexWrap = document.createElement("div")
            flexWrap.style.cssText = "display:flex;overflow-x:auto"

            // Gutter: one <span> per line, derived from raw text count (never from HTML split)
            const gutter = document.createElement("div")
            gutter.style.cssText = [
                "display:flex", "flex-direction:column", "user-select:none",
                "padding:1rem 0.75rem 1rem 1rem", "text-align:right",
                "color:#636d83", "font-size:0.75rem", "line-height:1.6",
                "min-width:2.5rem", "border-right:1px solid rgba(255,255,255,0.08)",
                "flex-shrink:0",
            ].join(";")
            for (let i = 1; i <= lineCount; i++) {
                const span = document.createElement("span")
                span.textContent = String(i)
                gutter.appendChild(span)
            }

            // Code scroll area
            const scrollWrap = document.createElement("div")
            scrollWrap.style.cssText = "flex:1;overflow-x:auto;padding:1rem 1.25rem;min-width:0"
            codeEl.style.display = "block"
            codeEl.style.whiteSpace = "pre"

            pre.insertBefore(flexWrap, codeEl)
            flexWrap.appendChild(gutter)
            flexWrap.appendChild(scrollWrap)
            scrollWrap.appendChild(codeEl)

            // — Copy button —
            const ICON_COPY = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`
            const ICON_CHECK = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`

            const btn = document.createElement("button")
            btn.title = "Copy code"
            btn.innerHTML = ICON_COPY
            Object.assign(btn.style, {
                position: "absolute", top: "10px", right: "10px",
                background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: "6px", padding: "5px 8px", cursor: "pointer",
                color: "#9da5b4", display: "flex", alignItems: "center",
                justifyContent: "center", transition: "all 0.15s",
            })
            btn.addEventListener("mouseenter", () => { btn.style.background = "rgba(255,255,255,0.15)"; btn.style.color = "#fff" })
            btn.addEventListener("mouseleave", () => { btn.style.background = "rgba(255,255,255,0.08)"; btn.style.color = "#9da5b4" })
            btn.addEventListener("click", async () => {
                try {
                    await navigator.clipboard.writeText(rawText)
                    btn.innerHTML = ICON_CHECK
                    btn.style.color = "#4ade80"
                    setTimeout(() => { btn.innerHTML = ICON_COPY; btn.style.color = "#9da5b4" }, 2000)
                } catch { /* clipboard denied */ }
            })
            pre.appendChild(btn)
        })
    }, [content])

    async function loadContent() {
        setLoading(true)
        const { success, data } = await getRequest(`/py/chapter/${chapter.id}`)
        if (success) setContent(data.newsletter)
        setLoading(false)
    }

    async function handleGenerate() {
        setConfirmOpen(false)
        onGenerationStart(chapter.id)
        try {
            await api.post("/py/generate-content/chapter", { task_id: chapter.id })
            setHasContent(true)
            onContentGenerated(chapter.id)
            loadContent()
        } catch (err: any) {
            const status = err?.response?.status
            const detail = err?.response?.data?.detail ?? ""
            if (status === 400 && typeof detail === "string" && detail.includes("LLM provider")) {
                toast({
                    title: "LLM not configured",
                    description: "Add your provider and API key in Settings.",
                    action: (
                        <ToastAction altText="Open Settings" onClick={() => setSettingsOpen(true)}>
                            Open Settings
                        </ToastAction>
                    ),
                })
            } else if (status === 429) {
                toast({ variant: "destructive", title: "Quota exceeded", description: detail || "You've hit your LLM provider's rate limit. Wait a moment and try again." })
            } else {
                toast({ variant: "destructive", title: "Error", description: detail || "Failed to generate content." })
            }
        } finally {
            onGenerationEnd(chapter.id)
        }
    }

    // async function handleSendEmail() {
    //     setSending(true)
    //     const { success } = await postRequest("/py/send-email/chapter", { task_id: chapter.id })
    //     setSending(false)
    //     if (success) setEmailSent(true)
    // }

    async function handleMarkComplete() {
        const { success } = await postRequest(`/py/chapter/${chapter.id}/complete`, {
            local_date: new Date().toLocaleDateString("en-CA"),
        })
        if (success) {
            setCompleted(true)
            onMarkComplete(chapter.id)
        }
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* Header */}
            <div className="border-b px-4 sm:px-8 py-5 bg-background shrink-0">
                <p className="text-xs text-muted-foreground mb-1">Day {chapter.day} · {chapter.hours}h</p>
                <h2 className="text-xl sm:text-2xl font-bold tracking-tight">{chapter.topic}</h2>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto overflow-x-hidden">
                <div className="mx-auto w-full max-w-3xl px-4 sm:px-6 md:px-8 py-6 space-y-5 min-w-0">

                    {/* Task */}
                    <div className="rounded-lg border bg-muted/30 px-4 py-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Task</p>
                        <p className="text-sm text-muted-foreground leading-relaxed">{chapter.task}</p>
                    </div>

                    {hasContent ? (
                        loading ? (
                            <div className="space-y-3 pt-2">
                                {[...Array(8)].map((_, i) => (
                                    <div key={i} className={`h-3 bg-muted rounded animate-pulse ${i % 3 === 0 ? "w-3/4" : i % 3 === 1 ? "w-full" : "w-5/6"}`} />
                                ))}
                            </div>
                        ) : content ? (
                            <div className="space-y-4">
                                {/* Toolbar */}
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                        <FileText className="h-3 w-3" /> Content
                                    </div>
                                    <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1.5" disabled={generating} onClick={() => setConfirmOpen(true)}>
                                        {generating
                                            ? <><Loader2 className="h-3 w-3 animate-spin" />Regenerating…</>
                                            : <><Sparkles className="h-3 w-3" />Regenerate</>
                                        }
                                    </Button>
                                </div>

                                {/* Prose content */}
                                <div
                                    ref={proseRef}
                                    className="prose prose-sm sm:prose-base max-w-none break-words
                                        prose-headings:text-foreground prose-headings:font-semibold prose-headings:tracking-tight
                                        prose-h1:text-lg sm:prose-h1:text-2xl prose-h1:mt-6 sm:prose-h1:mt-8 prose-h1:mb-3 sm:prose-h1:mb-4
                                        prose-h2:text-base sm:prose-h2:text-xl prose-h2:mt-5 sm:prose-h2:mt-6 prose-h2:mb-2 sm:prose-h2:mb-3 prose-h2:border-b prose-h2:border-border/50 prose-h2:pb-2
                                        prose-h3:text-sm sm:prose-h3:text-base prose-h3:mt-4 sm:prose-h3:mt-5 prose-h3:mb-1.5 sm:prose-h3:mb-2
                                        prose-h4:text-xs sm:prose-h4:text-sm prose-h4:mt-3 sm:prose-h4:mt-4 prose-h4:mb-1
                                        prose-p:text-zinc-600 prose-p:leading-6 sm:prose-p:leading-7
                                        prose-strong:text-foreground prose-strong:font-semibold
                                        prose-em:text-zinc-600
                                        prose-a:text-primary prose-a:no-underline hover:prose-a:underline prose-a:font-medium
                                        prose-ul:pl-5 prose-ol:pl-5 prose-ul:my-3 prose-ol:my-3
                                        prose-li:text-zinc-600 prose-li:leading-7 prose-li:my-0.5
                                        [&_ul>li::marker]:text-zinc-500 [&_ol>li::marker]:text-zinc-500
                                        prose-code:bg-zinc-100 prose-code:text-zinc-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
                                        [&_pre]:!p-0 [&_pre]:!bg-[#282c34] [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-white/10 [&_pre]:shadow-lg [&_pre]:text-sm [&_pre]:max-w-full [&_pre]:overflow-x-auto
                                        [&_pre_code]:!bg-transparent [&_pre_code]:!p-0 [&_pre_code]:font-mono
                                        prose-blockquote:border-l-4 prose-blockquote:border-primary/40 prose-blockquote:bg-muted/30 prose-blockquote:rounded-r-lg prose-blockquote:py-2 prose-blockquote:px-4 prose-blockquote:not-italic prose-blockquote:text-zinc-600 prose-blockquote:my-4
                                        prose-hr:border-border prose-hr:my-6
                                        prose-table:w-full prose-table:border-collapse prose-table:text-xs sm:prose-table:text-sm
                                        prose-thead:bg-muted/50
                                        prose-th:border prose-th:border-border prose-th:px-2 sm:prose-th:px-4 prose-th:py-2 sm:prose-th:py-2.5 prose-th:text-left prose-th:font-semibold prose-th:text-foreground
                                        prose-td:border prose-td:border-border prose-td:px-2 sm:prose-td:px-4 prose-td:py-1.5 sm:prose-td:py-2 prose-td:text-zinc-600
                                        prose-tr:even:bg-muted/20
                                        [&_table]:rounded-lg [&_table]:border [&_table]:border-border
                                        [&_:where(table)]:block [&_:where(table)]:overflow-x-auto"
                                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(content) }}
                                />

                                {/* Footer */}
                                <div className="pt-4 border-t border-border/50 flex flex-wrap items-center justify-between gap-2 sm:gap-3">
                                    {completed ? (
                                        <span className="flex items-center gap-1.5 text-sm text-emerald-600 font-medium">
                                            <CheckCircle2 className="h-4 w-4" /> Completed
                                        </span>
                                    ) : (
                                        <Button size="sm" variant="outline" onClick={handleMarkComplete}>
                                            <CheckCircle2 className="h-4 w-4 mr-1.5" />Mark Complete
                                        </Button>
                                    )}
                                    {completed && hasNext && (
                                        <Button size="sm" onClick={onGoToNext}>
                                            Next Chapter <ArrowRight className="h-4 w-4 ml-1.5" />
                                        </Button>
                                    )}
                                    {/* Send Email — not yet implemented in backend
                                    <Button size="sm" disabled={sending || emailSent} onClick={handleSendEmail} className={emailSent ? "bg-emerald-600 hover:bg-emerald-700" : ""}>
                                        {sending ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" />Sending…</>
                                            : emailSent ? <><CheckCircle2 className="h-4 w-4 mr-1.5" />Email Sent</>
                                            : <><Send className="h-4 w-4 mr-1.5" />Send Email</>
                                        }
                                    </Button>
                                    */}
                                </div>
                            </div>
                        ) : null
                    ) : (
                        <div className="flex flex-col items-center justify-center py-12 sm:py-24 text-center rounded-lg border border-dashed">
                            <Sparkles className="h-10 w-10 text-muted-foreground mb-3" />
                            <h3 className="font-semibold">Content not generated yet</h3>
                            <p className="text-sm text-muted-foreground mt-1 mb-4">Generate the content for this chapter to read it here.</p>
                            <Button onClick={handleGenerate} disabled={generating}>
                                {generating
                                    ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" />Generating…</>
                                    : <><Sparkles className="h-4 w-4 mr-1.5" />Generate Content</>
                                }
                            </Button>
                        </div>
                    )}
                </div>
            </div>

            {/* Confirmation dialog */}
            <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Regenerate content?</DialogTitle>
                        <DialogDescription>
                            This will replace the existing content for this chapter. This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2">
                        <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
                        <Button onClick={handleGenerate}>
                            <Sparkles className="h-4 w-4 mr-1.5" />
                            Yes, Regenerate
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

// ─── Chapter Nav (left panel) ─────────────────────────────────────────────────

function ChapterNav({ detail, activeChapterId, onSelectChapter, onSelectQuiz, isQuizActive, overallProgress, completedCount, totalCount, shareEnabled, togglingShare, copied, copyFailed, skillId, onToggleShare, onCopyLink, quizStatus }: {
    detail: SyllabusDetail
    activeChapterId: number | null
    onSelectChapter: (chapter: Chapter) => void
    onSelectQuiz: () => void
    isQuizActive: boolean
    overallProgress: number
    completedCount: number
    totalCount: number
    shareEnabled: boolean
    togglingShare: boolean
    copied: boolean
    copyFailed: boolean
    skillId: string
    onToggleShare: () => void
    onCopyLink: () => void
    quizStatus: string
}) {
    const [openMonths, setOpenMonths] = useState<Set<number>>(
        () => new Set(detail.months.map((m) => m.month))
    )

    function toggleMonth(month: number) {
        setOpenMonths((prev) => {
            const next = new Set(prev)
            if (next.has(month)) next.delete(month)
            else next.add(month)
            return next
        })
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* Progress */}
            <div className="px-4 py-3 border-b shrink-0 space-y-2">
                <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Progress</span>
                    <span>{completedCount}/{totalCount} days</span>
                </div>
                <Progress value={overallProgress} className="h-1.5" />
                <p className="text-xs font-semibold text-primary text-right">{overallProgress}%</p>
            </div>

            {/* LLM bar */}
            <div className="px-4 py-3 border-b shrink-0 space-y-2">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Choose a model</p>
                <LlmBar fullWidth />
            </div>

            {/* Share controls */}
            <div className="px-4 py-3 border-b shrink-0">
                <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <Globe className={`h-3.5 w-3.5 ${shareEnabled ? "text-emerald-500" : "text-muted-foreground"}`} />
                        <span className="text-xs font-medium">{shareEnabled ? "Public" : "Private"}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        {shareEnabled && (
                            <Button size="sm" variant="outline" className="h-6 px-2 text-xs gap-1" onClick={onCopyLink}>
                                {copied ? <><Check className="h-3 w-3 text-emerald-500" />Copied</> : <><Copy className="h-3 w-3" />Copy link</>}
                            </Button>
                        )}
                        <Button
                            size="sm"
                            variant={shareEnabled ? "ghost" : "outline"}
                            className={`h-6 px-2 text-xs ${shareEnabled ? "text-muted-foreground hover:text-destructive" : ""}`}
                            disabled={togglingShare}
                            onClick={onToggleShare}
                        >
                            {togglingShare ? <Loader2 className="h-3 w-3 animate-spin" /> : shareEnabled ? "Disable" : "Generate Link"}
                        </Button>
                    </div>
                </div>
                {copyFailed && (
                    <input
                        readOnly
                        value={`${window.location.origin}/public/syllabi/${skillId}`}
                        onFocus={(e) => e.target.select()}
                        className="mt-2 w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none"
                    />
                )}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-3 px-4 py-2 border-b text-xs text-muted-foreground shrink-0">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" />Completed</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-indigo-400" />Generated</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-muted-foreground/30" />Pending</span>
            </div>

            {/* Chapter tree */}
            <div className="flex-1 overflow-y-auto">
                {detail.months.map((month) => (
                    <div key={month.month}>
                        <button
                            className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-muted/50 transition-colors"
                            onClick={() => toggleMonth(month.month)}
                        >
                            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Month {month.month}</span>
                            {openMonths.has(month.month)
                                ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
                                : <ChevronRight className="h-3 w-3 text-muted-foreground" />
                            }
                        </button>
                        {openMonths.has(month.month) && month.weeks.map((week) => (
                            <div key={week.week} className="mb-1">
                                <p className="px-4 py-1 text-xs text-muted-foreground/60 font-medium">Week {week.week}</p>
                                {week.tasks.map((chapter) => (
                                    <button
                                        key={chapter.id}
                                        onClick={() => onSelectChapter(chapter)}
                                        className={`w-full flex items-start gap-2.5 px-4 py-2 text-left text-sm transition-colors ${
                                            chapter.id === activeChapterId
                                                ? "bg-primary/10 text-primary border-r-2 border-primary"
                                                : "hover:bg-muted/50 text-foreground/80"
                                        }`}
                                    >
                                        <span className={`mt-1.5 h-2 w-2 rounded-full flex-shrink-0 ${
                                            chapter.completed ? "bg-emerald-500" : chapter.has_content ? "bg-indigo-400" : "bg-muted-foreground/30"
                                        }`} />
                                        <span className="leading-snug">
                                            <span className="text-xs text-muted-foreground mr-1">D{chapter.day}.</span>
                                            {chapter.topic}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        ))}
                    </div>
                ))}

                {/* Final Quiz — always shown at end of chapter list */}
                {totalCount > 0 && (
                    <div className="border-t mt-1">
                        {completedCount === totalCount ? (
                            <button
                                onClick={onSelectQuiz}
                                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                                    isQuizActive
                                        ? "bg-primary/10 text-primary border-r-2 border-primary"
                                        : "hover:bg-muted/50"
                                }`}
                            >
                                <GraduationCap className={`h-4 w-4 shrink-0 ${
                                    quizStatus === "passed" ? "text-emerald-500"
                                    : isQuizActive ? "text-primary"
                                    : "text-muted-foreground"
                                }`} />
                                <div className="flex-1 min-w-0">
                                    <p className={`text-sm font-medium ${isQuizActive ? "text-primary" : "text-foreground/80"}`}>
                                        Final Quiz
                                    </p>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {quizStatus === "passed" ? "Passed ✓"
                                            : quizStatus === "available" ? "Ready to attempt"
                                            : "Not generated yet"}
                                    </p>
                                </div>
                                {quizStatus === "passed" && (
                                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                                )}
                            </button>
                        ) : (
                            <div className="w-full flex items-center gap-3 px-4 py-3 opacity-50 cursor-not-allowed select-none">
                                <GraduationCap className="h-4 w-4 shrink-0 text-muted-foreground" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-foreground/80">Final Quiz</p>
                                    <p className="text-xs text-muted-foreground mt-0.5">Complete all chapters to attempt</p>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

function DetailSkeleton() {
    return (
        <div className="flex overflow-hidden h-screen" style={{ height: "100dvh" }}>
            <aside className="w-72 border-r flex-col shrink-0 hidden sm:flex">
                <div className="px-4 py-3 border-b space-y-2">
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-1.5 w-full rounded-full" />
                </div>
                <div className="p-4 space-y-2">
                    {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-8 w-full rounded" />)}
                </div>
            </aside>
            <main className="flex-1 p-8 space-y-4">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-4/6" />
            </main>
        </div>
    )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SyllabusDetailPage() {
    const { skillId } = useParams<{ skillId: string }>()
    const navigate = useNavigate()
    const [searchParams, setSearchParams] = useSearchParams()
    const [detail, setDetail] = useState<SyllabusDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const { setPluginName, setHideHeader } = useStore((state: any) => state)
    const [shareEnabled, setShareEnabled] = useState(false)
    const [togglingShare, setTogglingShare] = useState(false)
    const [copied, setCopied] = useState(false)
    const [copyFailed, setCopyFailed] = useState(false)
    const [activeChapterId, setActiveChapterId] = useState<number | null>(null)
    const [activeView, setActiveView] = useState<"chapter" | "quiz">("chapter")
    const [generatingIds, setGeneratingIds] = useState<Set<number>>(new Set())
    const [navCollapsed, setNavCollapsed] = useState(false)
    const [navWidth, setNavWidth] = useState(350)
    const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
    const isResizing = useRef(false)
    const { setOpen } = useSidebar()

    function handleResizeStart(e: React.MouseEvent) {
        e.preventDefault()
        isResizing.current = true
        function onMove(ev: MouseEvent) {
            if (!isResizing.current) return
            setNavWidth(Math.max(300, Math.min(520, ev.clientX)))
        }
        function onUp() {
            isResizing.current = false
            document.removeEventListener("mousemove", onMove)
            document.removeEventListener("mouseup", onUp)
        }
        document.addEventListener("mousemove", onMove)
        document.addEventListener("mouseup", onUp)
    }

    // Collapse app sidebar + hide header on enter, restore on leave
    useEffect(() => {
        setOpen(false)
        setHideHeader(true)
        return () => {
            setOpen(true)
            setHideHeader(false)
        }
    }, [])

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        async function fetchDetail() {
            const { success, data } = await getRequest(`/py/syllabi/${skillId}`)
            if (cancelled) return
            if (success) {
                setDetail(data)
                setShareEnabled(data.share_enabled ?? false)
                setPluginName(data.skill)
            }
            setLoading(false)
        }
        fetchDetail()
        return () => { cancelled = true }
    }, [skillId, setPluginName])

    const allTasks = detail?.months.flatMap((m) => m.weeks.flatMap((w) => w.tasks)) ?? []
    const completedCount = allTasks.filter((t) => t.completed).length
    const quizPassed = detail?.quiz_status === "passed"
    // Quiz counts as one extra step — chapters + quiz = total course
    const totalSteps = allTasks.length + 1
    const completedSteps = completedCount + (quizPassed ? 1 : 0)
    const overallProgress = totalSteps > 1 ? Math.round((completedSteps / totalSteps) * 100) : 0

    // Restore chapter from URL param, fallback to first chapter
    useEffect(() => {
        if (allTasks.length === 0) return
        const paramId = Number(searchParams.get("chapter"))
        const found = paramId && allTasks.find(t => t.id === paramId)
        setActiveChapterId(found ? paramId : allTasks[0].id)
    }, [detail])

    const activeChapter = activeChapterId ? allTasks.find((t) => t.id === activeChapterId) ?? null : null
    const activeIndex = activeChapterId ? allTasks.findIndex((t) => t.id === activeChapterId) : -1
    const nextChapter = activeIndex >= 0 && activeIndex < allTasks.length - 1 ? allTasks[activeIndex + 1] : null

    function goToNextChapter() {
        if (!nextChapter) return
        setActiveChapterId(nextChapter.id)
        setSearchParams({ chapter: String(nextChapter.id) })
    }

    function handleContentGenerated(taskId: number) {
        setDetail((prev) => {
            if (!prev) return prev
            return {
                ...prev,
                months: prev.months.map((m) => ({
                    ...m,
                    weeks: m.weeks.map((w) => ({
                        ...w,
                        tasks: w.tasks.map((t) => t.id === taskId ? { ...t, has_content: true } : t),
                    })),
                })),
            }
        })
    }

    function handleQuizStatusChange(status: string) {
        setDetail((prev) => prev ? { ...prev, quiz_status: status } : prev)
    }

    function handleGenerationStart(taskId: number) {
        setGeneratingIds((prev) => new Set(prev).add(taskId))
    }

    function handleGenerationEnd(taskId: number) {
        setGeneratingIds((prev) => { const next = new Set(prev); next.delete(taskId); return next })
    }

    function handleChapterCompleted(taskId: number) {
        setDetail((prev) => {
            if (!prev) return prev
            return {
                ...prev,
                months: prev.months.map((m) => ({
                    ...m,
                    weeks: m.weeks.map((w) => ({
                        ...w,
                        tasks: w.tasks.map((t) => t.id === taskId ? { ...t, completed: true } : t),
                    })),
                })),
            }
        })
    }

    async function handleToggleShare() {
        setTogglingShare(true)
        const nextValue = !shareEnabled
        try {
            await api.patch(`/py/syllabi/${skillId}/share?enable=${nextValue}`)
            setShareEnabled(nextValue)
        } catch {
            // leave unchanged on error
        } finally {
            setTogglingShare(false)
        }
    }

    async function handleCopyLink() {
        const url = `${window.location.origin}/public/syllabi/${skillId}`
        try {
            await navigator.clipboard.writeText(url)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch {
            setCopyFailed(true)
            setTimeout(() => setCopyFailed(false), 2000)
        }
    }

    if (loading) return <DetailSkeleton />

    if (!detail) return (
        <div className="p-6">
            <Button variant="ghost" size="sm" onClick={() => navigate("/syllabi")}>
                <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <p className="mt-4 text-muted-foreground">Syllabus not found.</p>
        </div>
    )

    return (
        <div className="flex overflow-hidden h-screen" style={{ height: "100dvh" }}>

            {/* Mobile backdrop */}
            {mobileSidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 sm:hidden"
                    onClick={() => setMobileSidebarOpen(false)}
                />
            )}

            {/* Left nav panel */}
            <aside
                style={{ width: navWidth }}
                className={[
                    "flex-col h-full overflow-hidden bg-background",
                    // Mobile: fixed full-height overlay, display:none when closed so it doesn't affect flex layout
                    mobileSidebarOpen
                        ? "fixed left-0 top-0 bottom-0 z-50 flex w-[85vw] shadow-xl"
                        : "hidden",
                    // Desktop: override to inline sidebar
                    navCollapsed
                        ? "sm:hidden"
                        : "sm:relative sm:flex sm:flex-shrink-0 sm:border-r",
                ].join(" ")}
            >
                <div style={{ width: navWidth }} className="relative flex flex-col h-full w-full">
                    {/* Nav header */}
                    <div className="flex items-center gap-2 px-4 py-3 border-b shrink-0">
                        <Button variant="ghost" size="sm" className="-ml-1 h-7 text-xs" onClick={() => navigate("/syllabi")}>
                            <ArrowLeft className="h-3.5 w-3.5 mr-1" /> All Courses
                        </Button>
                        <span className="text-sm font-semibold truncate text-foreground/80 flex-1">{detail.skill}</span>
                        {/* Desktop: collapse button */}
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 hidden sm:flex" onClick={() => setNavCollapsed(true)} title="Collapse sidebar">
                            <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                        </Button>
                        {/* Mobile: close button */}
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 flex sm:hidden" onClick={() => setMobileSidebarOpen(false)} title="Close">
                            <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                        </Button>
                    </div>
                    <ChapterNav
                        detail={detail}
                        activeChapterId={activeChapterId}
                        onSelectChapter={(chapter) => { setActiveChapterId(chapter.id); setActiveView("chapter"); setSearchParams({ chapter: String(chapter.id) }); setMobileSidebarOpen(false); }}
                        overallProgress={overallProgress}
                        completedCount={completedCount}
                        totalCount={allTasks.length}
                        shareEnabled={shareEnabled}
                        togglingShare={togglingShare}
                        copied={copied}
                        copyFailed={copyFailed}
                        skillId={skillId!}
                        onToggleShare={handleToggleShare}
                        onCopyLink={handleCopyLink}
                        quizStatus={detail.quiz_status}
                        onSelectQuiz={() => { setActiveView("quiz"); setMobileSidebarOpen(false) }}
                        isQuizActive={activeView === "quiz"}
                    />
                    {/* Resize handle */}
                    <div
                        className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/40 active:bg-primary/60 z-10"
                        onMouseDown={handleResizeStart}
                    />
                </div>
            </aside>

            {/* Right content panel */}
            <main className="flex-1 w-0 min-w-0 flex flex-col overflow-hidden">
                {/* Top bar */}
                <div className="flex items-center gap-2 px-3 sm:px-4 py-3 border-b shrink-0">
                    {/* Mobile: open sidebar button */}
                    <Button variant="ghost" size="icon" className="h-7 w-7 flex sm:hidden shrink-0" onClick={() => setMobileSidebarOpen(true)} title="Open chapters">
                        <PanelLeftOpen className="h-4 w-4 text-muted-foreground" />
                    </Button>
                    {/* Desktop: collapse/expand toggle */}
                    <Button variant="ghost" size="icon" className="h-7 w-7 hidden sm:flex shrink-0" onClick={() => setNavCollapsed((v) => !v)} title={navCollapsed ? "Expand sidebar" : "Collapse sidebar"}>
                        {navCollapsed ? <PanelLeftOpen className="h-4 w-4 text-muted-foreground" /> : <PanelLeftClose className="h-4 w-4 text-muted-foreground" />}
                    </Button>
                    {navCollapsed && (
                        <>
                            <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={() => navigate("/syllabi")}>
                                <ArrowLeft className="h-3.5 w-3.5 mr-1" /> <span className="hidden sm:inline">All Courses</span>
                            </Button>
                            <span className="text-sm font-semibold text-foreground/80 truncate">{detail.skill}</span>
                            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0 hidden sm:block" />
                            {activeView === "quiz" ? (
                                <span className="text-sm text-muted-foreground truncate hidden sm:block">Final Quiz</span>
                            ) : activeChapter && (
                                <span className="text-sm text-muted-foreground truncate hidden sm:block">
                                    <span className="mr-1">Day {activeChapter.day}.</span>{activeChapter.topic}
                                </span>
                            )}
                        </>
                    )}
                    {!navCollapsed && (
                        activeView === "quiz" ? (
                            <span className="text-sm text-muted-foreground truncate">Final Quiz</span>
                        ) : activeChapter ? (
                            <span className="text-sm text-muted-foreground truncate">
                                <span className="mr-1">Day {activeChapter.day}.</span>{activeChapter.topic}
                            </span>
                        ) : null
                    )}
                </div>

                <div className="flex-1 overflow-hidden">
                    {activeView === "quiz" ? (
                        <QuizPanel
                            skillId={skillId!}
                            onBack={() => setActiveView("chapter")}
                            onQuizStatusChange={handleQuizStatusChange}
                        />
                    ) : activeChapter ? (
                        <ChapterContentPanel
                            key={activeChapter.id}
                            chapter={activeChapter}
                            isGenerating={generatingIds.has(activeChapter.id)}
                            onGenerationStart={handleGenerationStart}
                            onGenerationEnd={handleGenerationEnd}
                            onContentGenerated={handleContentGenerated}
                            onMarkComplete={handleChapterCompleted}
                            onGoToNext={goToNextChapter}
                            hasNext={!!nextChapter}
                        />
                    ) : null}
                </div>
            </main>
        </div>
    )
}
