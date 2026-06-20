import { useEffect, useRef, useState } from "react"
import { useParams, useNavigate } from "react-router"
import {
    ArrowLeft, ArrowRight, CheckCircle2, FileText, Sparkles, Loader2,
    Globe, Copy, Check, PanelLeftClose, PanelLeftOpen, GraduationCap,
    Brain, Settings,
} from "lucide-react"
import { BlockRenderer, type ContentBlock } from "@/app/plugins/syllabi/block-renderer"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { LlmBar } from "@/components/llm-bar"
import { useToast } from "@/hooks/use-toast"
import { ToastAction } from "@/components/ui/toast"
import {
    Dialog, DialogContent, DialogDescription, DialogFooter,
    DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { getRequest, postRequest } from "@/services"
import api from "@/services"
import useStore from "@/store"
import { useSidebar } from "@/components/ui/sidebar"
import { cn } from "@/lib/utils"

interface OnboardingDay {
    id: number
    plan_id: number
    day: number
    topic: string
    task: string
    content_blocks: string | null
    completed: boolean
}

interface OnboardingPlan {
    id: number
    role: string
    company: string
    status: string
    share_enabled: boolean
    created_at: string
}

// ─── Day Content Panel (right) ────────────────────────────────────────────────

function DayContentPanel({
    day, isGenerating, planId, onGenerationStart, onGenerationEnd,
    onContentGenerated, onMarkComplete, onGoToNext, hasNext, onGoToQuiz, isLastDay,
}: {
    day: OnboardingDay
    isGenerating: boolean
    planId: number
    onGenerationStart: (id: number) => void
    onGenerationEnd: (id: number) => void
    onContentGenerated: (id: number) => void
    onMarkComplete: (id: number) => void
    onGoToNext: () => void
    hasNext: boolean
    onGoToQuiz: () => void
    isLastDay: boolean
}) {
    const [blocks, setBlocks] = useState<ContentBlock[] | null>(null)
    const [loading, setLoading] = useState(false)
    const [completed, setCompleted] = useState(day.completed)
    const [hasContent, setHasContent] = useState(!!day.content_blocks)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const { toast } = useToast()
    const { setSettingsOpen } = useStore((s: any) => s)

    useEffect(() => {
        setCompleted(day.completed)
        setHasContent(!!day.content_blocks)
        setBlocks(null)
        if (day.content_blocks) loadContent()
    }, [day.id])

    async function loadContent() {
        setLoading(true)
        const { success, data } = await getRequest(`/py/onboarding/${planId}/day/${day.day}`)
        if (success && data.day.content_blocks) {
            try {
                const parsed = JSON.parse(data.day.content_blocks)
                if (Array.isArray(parsed) && parsed.length > 0) setBlocks(parsed)
            } catch { /* ignore */ }
        }
        setLoading(false)
    }

    async function handleGenerate() {
        setConfirmOpen(false)
        onGenerationStart(day.id)
        try {
            const response = await api.get(`/py/onboarding/${planId}/day/${day.day}`)
            const data = response.data
            if (data?.day?.content_blocks) {
                try {
                    const parsed = JSON.parse(data.day.content_blocks)
                    if (Array.isArray(parsed) && parsed.length > 0) {
                        setBlocks(parsed)
                        setHasContent(true)
                        onContentGenerated(day.id)
                    }
                } catch { /* ignore */ }
            }
        } catch (err: any) {
            const status = err?.response?.status
            const rawDetail = err?.response?.data?.detail
            const detail = typeof rawDetail === "string" ? rawDetail : ""
            if (status === 400 && detail.includes("LLM provider")) {
                toast({
                    title: "LLM not configured",
                    description: "Add your provider and API key in Settings.",
                    action: <ToastAction altText="Open Settings" onClick={() => setSettingsOpen(true)}>Open Settings</ToastAction>,
                })
            } else {
                toast({ variant: "destructive", title: "Error", description: detail || "Failed to generate content." })
            }
        } finally {
            onGenerationEnd(day.id)
        }
    }

    async function handleMarkComplete() {
        const { success } = await postRequest(`/py/onboarding/${planId}/day/${day.day}/complete`, {})
        if (success) {
            setCompleted(true)
            onMarkComplete(day.id)
        }
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="border-b px-4 sm:px-8 py-5 bg-background shrink-0">
                <p className="text-xs text-muted-foreground mb-1">Day {day.day} of 7</p>
                <h2 className="text-xl sm:text-2xl font-bold tracking-tight">{day.topic}</h2>
            </div>

            <div className="flex-1 overflow-y-auto overflow-x-hidden">
                <div className="mx-auto w-full max-w-3xl px-4 sm:px-6 md:px-8 py-6 space-y-5 min-w-0">
                    <div className="rounded-lg border bg-muted/30 px-4 py-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Task</p>
                        <p className="text-sm text-muted-foreground leading-relaxed">{day.task}</p>
                    </div>

                    {hasContent ? (
                        loading ? (
                            <div className="space-y-3 pt-2">
                                {[...Array(8)].map((_, i) => (
                                    <div key={i} className={`h-3 bg-muted rounded animate-pulse ${i % 3 === 0 ? "w-3/4" : i % 3 === 1 ? "w-full" : "w-5/6"}`} />
                                ))}
                            </div>
                        ) : blocks ? (
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                        <FileText className="h-3 w-3" /> Content
                                    </div>
                                    <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1.5" disabled={isGenerating} onClick={() => setConfirmOpen(true)}>
                                        {isGenerating
                                            ? <><Loader2 className="h-3 w-3 animate-spin" />Regenerating…</>
                                            : <><Sparkles className="h-3 w-3" />Regenerate</>
                                        }
                                    </Button>
                                </div>
                                <BlockRenderer blocks={blocks} />
                                <div className="pt-4 border-t border-border/50 flex flex-wrap items-center justify-between gap-2">
                                    {completed ? (
                                        <span className="flex items-center gap-1.5 text-sm text-emerald-600 font-medium">
                                            <CheckCircle2 className="h-4 w-4" /> Completed
                                        </span>
                                    ) : (
                                        <Button size="sm" variant="outline" onClick={handleMarkComplete}>
                                            <CheckCircle2 className="h-4 w-4 mr-1.5" />Mark Complete
                                        </Button>
                                    )}
                                    <div className="flex items-center gap-2">
                                        {completed && isLastDay && (
                                            <Button size="sm" onClick={onGoToQuiz}>
                                                <Brain className="h-4 w-4 mr-1.5" />Final Quiz
                                            </Button>
                                        )}
                                        {completed && hasNext && !isLastDay && (
                                            <Button size="sm" onClick={onGoToNext}>
                                                Next Day <ArrowRight className="h-4 w-4 ml-1.5" />
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ) : null
                    ) : (
                        <div className="flex flex-col items-center justify-center py-12 sm:py-24 text-center rounded-lg border border-dashed">
                            <Sparkles className="h-10 w-10 text-muted-foreground mb-3" />
                            <h3 className="font-semibold">Content not generated yet</h3>
                            <p className="text-sm text-muted-foreground mt-1 mb-4">Generate the learning content for this day.</p>
                            <Button onClick={handleGenerate} disabled={isGenerating}>
                                {isGenerating
                                    ? <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" />Generating…</>
                                    : <><Sparkles className="h-4 w-4 mr-1.5" />Generate Content</>
                                }
                            </Button>
                        </div>
                    )}
                </div>
            </div>

            <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Regenerate content?</DialogTitle>
                        <DialogDescription>This will replace the existing content for this day. This action cannot be undone.</DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2">
                        <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
                        <Button onClick={handleGenerate}><Sparkles className="h-4 w-4 mr-1.5" />Yes, Regenerate</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

// ─── Final Quiz Panel ─────────────────────────────────────────────────────────

type QuizAttempt = { id: number; score: number; correct: number; total: number; created_at: string }

function OnboardingQuizPanel({ planId }: { planId: number }) {
    const [questions, setQuestions] = useState<any[]>([])
    const [attempts, setAttempts] = useState<QuizAttempt[]>([])
    const [loading, setLoading] = useState(false)
    const [selected, setSelected] = useState<Record<number, string>>({})
    const [results, setResults] = useState<{ score: number; passed: boolean; answers: Record<number, { correct: string; is_correct: boolean }> } | null>(null)
    const { toast } = useToast()

    async function loadQuiz() {
        setLoading(true)
        const { success, data } = await getRequest(`/py/onboarding/${planId}/quiz`)
        if (success) {
            setQuestions(data.questions)
            setAttempts(data.attempts ?? [])
        } else toast({ variant: "destructive", title: "Error", description: "Failed to generate quiz." })
        setLoading(false)
    }

    async function handleSubmit() {
        if (questions.length === 0) return
        let correct = 0
        const answers: Record<number, { correct: string; is_correct: boolean }> = {}
        const submittedAnswers: Record<string, string> = {}
        questions.forEach((q, i) => {
            const correctKey = q.correct_answer ?? q.correct ?? "a"
            const isCorrect = selected[i] === correctKey
            if (isCorrect) correct++
            answers[i] = { correct: correctKey, is_correct: isCorrect }
            submittedAnswers[String(i)] = selected[i] ?? ""
        })
        const score = Math.round((correct / questions.length) * 100)
        setResults({ score, passed: score >= 70, answers })

        try {
            const { success, data } = await postRequest(`/py/onboarding/${planId}/quiz/attempt`, { answers: submittedAnswers })
            if (success) setAttempts(prev => [data.attempt, ...prev])
        } catch { /* non-critical */ }
    }

    if (loading) return (
        <div className="flex-1 flex flex-col items-center justify-center gap-4 p-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Generating quiz…</p>
        </div>
    )

    const bestScore = attempts.length > 0 ? Math.max(...attempts.map(a => a.score)) : null

    if (questions.length === 0) return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="border-b px-4 sm:px-8 py-5 shrink-0">
                <p className="text-xs text-muted-foreground mb-1">Final Assessment</p>
                <h2 className="text-xl sm:text-2xl font-bold tracking-tight">Final Quiz</h2>
            </div>
            <div className="flex-1 flex flex-col items-center justify-center text-center px-8">
                <GraduationCap className="h-12 w-12 text-muted-foreground mb-4" />
                <h3 className="font-semibold text-lg mb-1">Ready to test your knowledge?</h3>
                <p className="text-sm text-muted-foreground mb-6 max-w-xs">A 10-question quiz covering all 7 days of your onboarding plan.</p>
                {bestScore !== null && (
                    <p className="text-xs text-muted-foreground mb-4">
                        Best score: <span className={cn("font-semibold", bestScore >= 70 ? "text-emerald-600" : "text-amber-600")}>{bestScore}%</span>
                        {" "}· {attempts.length} attempt{attempts.length !== 1 ? "s" : ""}
                    </p>
                )}
                <Button onClick={loadQuiz}><Brain className="h-4 w-4 mr-2" />{attempts.length > 0 ? "Retake Quiz" : "Generate Quiz"}</Button>
            </div>
        </div>
    )

    const opts = ["a", "b", "c", "d"] as const
    const optLabels = { a: "A", b: "B", c: "C", d: "D" }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="border-b px-4 sm:px-8 py-5 shrink-0">
                <p className="text-xs text-muted-foreground mb-1">Final Assessment</p>
                <h2 className="text-xl sm:text-2xl font-bold tracking-tight">Final Quiz</h2>
            </div>
            <div className="flex-1 overflow-y-auto">
                <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 md:px-8 py-6 space-y-6">
                    {results && (
                        <div className={cn("rounded-xl border p-4 text-center", results.passed ? "bg-emerald-500/10 border-emerald-200" : "bg-amber-500/10 border-amber-200")}>
                            <p className="text-3xl font-bold">{results.score}%</p>
                            <p className={cn("text-sm font-medium mt-1", results.passed ? "text-emerald-600" : "text-amber-600")}>
                                {results.passed ? "Passed! Great work." : "Not passed — review and try again."}
                            </p>
                        </div>
                    )}
                    {questions.map((q, i) => {
                        const res = results?.answers[i]
                        return (
                            <div key={i} className="space-y-2">
                                <p className="text-sm font-medium">{i + 1}. {q.question}</p>
                                <div className="grid grid-cols-1 gap-2">
                                    {opts.map((opt) => {
                                        const text = q[`option_${opt}`] ?? q[opt]
                                        if (!text) return null
                                        const isSelected = selected[i] === opt
                                        const isCorrect = res?.correct === opt
                                        const isWrong = res && isSelected && !res.is_correct
                                        return (
                                            <button
                                                key={opt}
                                                disabled={!!results}
                                                onClick={() => !results && setSelected(s => ({ ...s, [i]: opt }))}
                                                className={cn(
                                                    "flex items-center gap-3 rounded-lg border px-4 py-2.5 text-left text-sm transition-colors",
                                                    results
                                                        ? isCorrect ? "border-emerald-400 bg-emerald-500/10 text-emerald-700"
                                                        : isWrong ? "border-red-400 bg-red-500/10 text-red-700"
                                                        : "opacity-50"
                                                        : isSelected ? "border-primary bg-primary/10 text-primary"
                                                        : "hover:border-border hover:bg-muted/50"
                                                )}
                                            >
                                                <span className="font-semibold text-xs shrink-0">{optLabels[opt]}</span>
                                                <span>{text}</span>
                                                {results && isCorrect && <CheckCircle2 className="h-4 w-4 ml-auto shrink-0 text-emerald-600" />}
                                            </button>
                                        )
                                    })}
                                </div>
                                {res && q.explanation && (
                                    <p className="text-xs text-muted-foreground bg-muted/40 rounded px-3 py-2">{q.explanation}</p>
                                )}
                            </div>
                        )
                    })}
                    {!results ? (
                        <Button className="w-full" onClick={handleSubmit} disabled={Object.keys(selected).length < questions.length}>
                            Submit Quiz
                        </Button>
                    ) : (
                        <Button variant="outline" className="w-full" onClick={() => { setSelected({}); setResults(null); setQuestions([]) }}>
                            <Brain className="h-4 w-4 mr-2" />Try Again
                        </Button>
                    )}
                </div>
            </div>
        </div>
    )
}

// ─── Day Nav (left panel) ─────────────────────────────────────────────────────

function DayNav({
    plan, days, activeDayId, onSelectDay, isQuizActive, onSelectQuiz,
    completedCount, shareEnabled, togglingShare, copied, copyFailed,
    onToggleShare, onCopyLink,
}: {
    plan: OnboardingPlan
    days: OnboardingDay[]
    activeDayId: number | null
    onSelectDay: (day: OnboardingDay) => void
    isQuizActive: boolean
    onSelectQuiz: () => void
    completedCount: number
    shareEnabled: boolean
    togglingShare: boolean
    copied: boolean
    copyFailed: boolean
    onToggleShare: () => void
    onCopyLink: () => void
}) {
    const total = days.length
    const progress = total > 0 ? Math.round((completedCount / total) * 100) : 0
    const { setSettingsOpen } = useStore((s: any) => s)

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="px-4 py-3 border-b shrink-0 space-y-2">
                <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Progress</span>
                    <span>{completedCount}/{total} days</span>
                </div>
                <Progress value={progress} className="h-1.5" />
                <p className="text-xs font-semibold text-primary text-right">{progress}%</p>
            </div>

            <div className="px-4 py-3 border-b shrink-0 space-y-2">
                <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Model</p>
                    <button type="button" title="Open Settings" onClick={() => setSettingsOpen(true)} className="text-muted-foreground hover:text-foreground transition-colors">
                        <Settings className="h-3.5 w-3.5" />
                    </button>
                </div>
                <LlmBar fullWidth />
            </div>

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
                    <input readOnly value={`${window.location.origin}/public/onboarding/${plan.id}`}
                        onFocus={(e) => e.target.select()}
                        className="mt-2 w-full rounded border border-input bg-background px-2 py-1 text-xs font-mono focus:outline-none"
                    />
                )}
            </div>

            <div className="flex-1 overflow-y-auto">
                {days.map((day) => (
                    <button
                        key={day.id}
                        onClick={() => onSelectDay(day)}
                        className={cn(
                            "w-full flex items-start gap-2.5 px-4 py-2.5 text-left text-sm transition-colors",
                            day.id === activeDayId
                                ? "bg-primary/10 text-primary border-r-2 border-primary"
                                : "hover:bg-muted/50 text-foreground/80"
                        )}
                    >
                        <span className={cn("mt-1.5 h-2 w-2 rounded-full flex-shrink-0",
                            day.completed ? "bg-emerald-500"
                                : day.content_blocks ? "bg-indigo-400"
                                : "bg-muted-foreground/30"
                        )} />
                        <span className="leading-snug">
                            <span className="text-xs text-muted-foreground mr-1">D{day.day}.</span>
                            {day.topic}
                        </span>
                    </button>
                ))}

                <div className="border-t mt-1">
                    {completedCount === days.length && days.length > 0 ? (
                        <button
                            onClick={onSelectQuiz}
                            className={cn(
                                "w-full flex items-center gap-3 px-4 py-3 text-left transition-colors",
                                isQuizActive
                                    ? "bg-primary/10 text-primary border-r-2 border-primary"
                                    : "hover:bg-muted/50"
                            )}
                        >
                            <GraduationCap className={cn("h-4 w-4 shrink-0", isQuizActive ? "text-primary" : "text-muted-foreground")} />
                            <div className="flex-1 min-w-0">
                                <p className={cn("text-sm font-medium", isQuizActive ? "text-primary" : "text-foreground/80")}>Final Quiz</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Test your knowledge</p>
                            </div>
                        </button>
                    ) : (
                        <div className="w-full flex items-center gap-3 px-4 py-3 opacity-40 cursor-not-allowed select-none">
                            <GraduationCap className="h-4 w-4 shrink-0 text-muted-foreground" />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-foreground/80">Final Quiz</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Complete all 7 days to unlock</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function DetailSkeleton() {
    return (
        <div className="flex overflow-hidden h-screen" style={{ height: "100dvh" }}>
            <aside className="w-72 border-r flex-col shrink-0 hidden sm:flex">
                <div className="px-4 py-3 border-b space-y-2">
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-1.5 w-full rounded-full" />
                </div>
                <div className="p-4 space-y-2">
                    {[...Array(7)].map((_, i) => <Skeleton key={i} className="h-8 w-full rounded" />)}
                </div>
            </aside>
            <main className="flex-1 p-8 space-y-4">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
            </main>
        </div>
    )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function OnboardingDetailPage() {
    const { planId } = useParams<{ planId: string }>()
    const navigate = useNavigate()
    const [plan, setPlan] = useState<OnboardingPlan | null>(null)
    const [days, setDays] = useState<OnboardingDay[]>([])
    const [loading, setLoading] = useState(true)
    const [activeDayId, setActiveDayId] = useState<number | null>(null)
    const [activeView, setActiveView] = useState<"day" | "quiz">("day")
    const [generatingIds, setGeneratingIds] = useState<Set<number>>(new Set())
    const [shareEnabled, setShareEnabled] = useState(false)
    const [togglingShare, setTogglingShare] = useState(false)
    const [copied, setCopied] = useState(false)
    const [copyFailed, setCopyFailed] = useState(false)
    const [navCollapsed, setNavCollapsed] = useState(false)
    const [navWidth, setNavWidth] = useState(320)
    const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
    const isResizing = useRef(false)
    const { setPluginName, setHideHeader } = useStore((state: any) => state)
    const { setOpen } = useSidebar()

    function handleResizeStart(e: React.MouseEvent) {
        e.preventDefault()
        isResizing.current = true
        function onMove(ev: MouseEvent) {
            if (!isResizing.current) return
            setNavWidth(Math.max(280, Math.min(480, ev.clientX)))
        }
        function onUp() {
            isResizing.current = false
            document.removeEventListener("mousemove", onMove)
            document.removeEventListener("mouseup", onUp)
        }
        document.addEventListener("mousemove", onMove)
        document.addEventListener("mouseup", onUp)
    }

    useEffect(() => {
        setOpen(false)
        setHideHeader(true)
        return () => { setOpen(true); setHideHeader(false) }
    }, [])

    useEffect(() => {
        getRequest(`/py/onboarding/${planId}`).then(({ success, data }) => {
            if (success) {
                setPlan(data.plan)
                setDays(data.days)
                setShareEnabled(data.plan.share_enabled ?? false)
                setPluginName(data.plan.role)
                if (data.days.length > 0) setActiveDayId(data.days[0].id)
            }
            setLoading(false)
        })
    }, [planId])

    const completedCount = days.filter(d => d.completed).length
    const activeDay = activeDayId ? days.find(d => d.id === activeDayId) ?? null : null
    const activeIndex = activeDayId ? days.findIndex(d => d.id === activeDayId) : -1
    const nextDay = activeIndex >= 0 && activeIndex < days.length - 1 ? days[activeIndex + 1] : null

    function handleContentGenerated(id: number) {
        setDays(prev => prev.map(d => d.id === id ? { ...d, content_blocks: "generated" } : d))
    }

    function handleMarkComplete(id: number) {
        setDays(prev => prev.map(d => d.id === id ? { ...d, completed: true } : d))
    }

    async function handleToggleShare() {
        if (!plan) return
        setTogglingShare(true)
        const next = !shareEnabled
        try {
            await api.patch(`/py/onboarding/${plan.id}/share?enable=${next}`)
            setShareEnabled(next)
        } catch { /* leave unchanged */ }
        finally { setTogglingShare(false) }
    }

    async function handleCopyLink() {
        const url = `${window.location.origin}/public/onboarding/${plan?.id}`
        try {
            await navigator.clipboard.writeText(url)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch {
            setCopyFailed(true)
            setTimeout(() => setCopyFailed(false), 3000)
        }
    }

    if (loading) return <DetailSkeleton />
    if (!plan) return (
        <div className="p-6">
            <Button variant="ghost" size="sm" onClick={() => navigate("/onboarding")}>
                <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <p className="mt-4 text-muted-foreground">Onboarding plan not found.</p>
        </div>
    )

    return (
        <div className="flex overflow-hidden h-screen" style={{ height: "100dvh" }}>
            {mobileSidebarOpen && (
                <div className="fixed inset-0 bg-black/50 z-40 sm:hidden" onClick={() => setMobileSidebarOpen(false)} />
            )}

            {/* Left nav panel */}
            <aside
                style={{ width: navWidth }}
                className={[
                    "flex-col h-full overflow-hidden bg-background",
                    mobileSidebarOpen
                        ? "fixed left-0 top-0 bottom-0 z-50 flex w-[85vw] shadow-xl"
                        : "hidden",
                    navCollapsed ? "sm:hidden" : "sm:relative sm:flex sm:flex-shrink-0 sm:border-r",
                ].join(" ")}
            >
                <div style={{ width: navWidth }} className="relative flex flex-col h-full w-full">
                    <div className="flex items-center gap-2 px-4 py-3 border-b shrink-0">
                        <Button variant="ghost" size="sm" className="-ml-1 h-7 text-xs" onClick={() => navigate("/onboarding")}>
                            <ArrowLeft className="h-3.5 w-3.5 mr-1" /> All Plans
                        </Button>
                        <span className="text-sm font-semibold truncate text-foreground/80 flex-1">{plan.role}</span>
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 hidden sm:flex" onClick={() => setNavCollapsed(true)} title="Collapse sidebar">
                            <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 flex sm:hidden" onClick={() => setMobileSidebarOpen(false)} title="Close">
                            <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                        </Button>
                    </div>
                    <DayNav
                        plan={plan}
                        days={days}
                        activeDayId={activeDayId}
                        onSelectDay={(d) => { setActiveDayId(d.id); setActiveView("day"); setMobileSidebarOpen(false) }}
                        isQuizActive={activeView === "quiz"}
                        onSelectQuiz={() => { setActiveView("quiz"); setMobileSidebarOpen(false) }}
                        completedCount={completedCount}
                        shareEnabled={shareEnabled}
                        togglingShare={togglingShare}
                        copied={copied}
                        copyFailed={copyFailed}
                        onToggleShare={handleToggleShare}
                        onCopyLink={handleCopyLink}
                    />
                    <div className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/40 active:bg-primary/60 z-10" onMouseDown={handleResizeStart} />
                </div>
            </aside>

            {/* Right content panel */}
            <main className="flex-1 w-0 min-w-0 flex flex-col overflow-hidden">
                <div className="flex items-center gap-2 px-3 sm:px-4 py-3 border-b shrink-0">
                    <Button variant="ghost" size="icon" className="h-7 w-7 flex sm:hidden shrink-0" onClick={() => setMobileSidebarOpen(true)} title="Open days">
                        <PanelLeftOpen className="h-4 w-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 hidden sm:flex shrink-0" onClick={() => setNavCollapsed(v => !v)} title={navCollapsed ? "Expand sidebar" : "Collapse sidebar"}>
                        {navCollapsed ? <PanelLeftOpen className="h-4 w-4 text-muted-foreground" /> : <PanelLeftClose className="h-4 w-4 text-muted-foreground" />}
                    </Button>
                    {navCollapsed && (
                        <>
                            <Button variant="ghost" size="sm" className="h-7 text-xs shrink-0" onClick={() => navigate("/onboarding")}>
                                <ArrowLeft className="h-3.5 w-3.5 mr-1" /><span className="hidden sm:inline">All Plans</span>
                            </Button>
                            <span className="text-sm font-semibold text-foreground/80 truncate">{plan.role}</span>
                        </>
                    )}
                    {activeView === "quiz" ? (
                        <span className="text-sm text-muted-foreground truncate">Final Quiz</span>
                    ) : activeDay ? (
                        <span className="text-sm text-muted-foreground truncate">
                            <span className="mr-1">Day {activeDay.day}.</span>{activeDay.topic}
                        </span>
                    ) : null}
                </div>

                <div className="flex-1 overflow-hidden">
                    {activeView === "quiz" ? (
                        <OnboardingQuizPanel planId={plan.id} />
                    ) : activeDay ? (
                        <DayContentPanel
                            key={activeDay.id}
                            day={activeDay}
                            planId={plan.id}
                            isGenerating={generatingIds.has(activeDay.id)}
                            onGenerationStart={(id) => setGeneratingIds(prev => new Set(prev).add(id))}
                            onGenerationEnd={(id) => setGeneratingIds(prev => { const n = new Set(prev); n.delete(id); return n })}
                            onContentGenerated={handleContentGenerated}
                            onMarkComplete={handleMarkComplete}
                            onGoToNext={() => nextDay && setActiveDayId(nextDay.id)}
                            hasNext={!!nextDay}
                            isLastDay={activeIndex === days.length - 1}
                            onGoToQuiz={() => setActiveView("quiz")}
                        />
                    ) : null}
                </div>
            </main>
        </div>
    )
}
