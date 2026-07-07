import { useEffect, useRef, useState } from "react"
import { useParams, useNavigate } from "react-router"
import {
    ArrowLeft, ArrowRight, CheckCircle2, XCircle, FileText, Sparkles, Loader2,
    Globe, Copy, Check, PanelLeftClose, PanelLeftOpen, GraduationCap,
    Brain, Settings, Zap, RotateCcw,
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

    async function handleGenerate(force = false) {
        setConfirmOpen(false)
        onGenerationStart(day.id)
        try {
            const url = force
                ? `/py/onboarding/${planId}/day/${day.day}?force=true`
                : `/py/onboarding/${planId}/day/${day.day}`
            const response = await api.get(url)
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
                            <Button onClick={() => handleGenerate()} disabled={isGenerating}>
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
                        <Button onClick={() => handleGenerate(true)}><Sparkles className="h-4 w-4 mr-1.5" />Yes, Regenerate</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

// ─── Final Quiz Panel ─────────────────────────────────────────────────────────

type QuizView = "loading" | "not_generated" | "generating" | "ready" | "taking" | "submitted" | "error" | "generate_error"

interface QuizQuestion {
    question: string
    option_a: string
    option_b: string
    option_c: string
    option_d: string
    // correct_answer is intentionally NOT sent to the client — grading is server-side.
    explanation: string
}

interface QuizAttempt { id: number; score: number; correct: number; total: number; answers: string | null; created_at: string | null }

interface QuestionResult { index: number; selected: string; correct: string; is_correct: boolean }

interface SubmitResult { score: number; passed: boolean; results: QuestionResult[] }

const PASS_SCORE = 70
const QUIZ_OPTS = ["a", "b", "c", "d"] as const
const OPT_LABELS: Record<string, string> = { a: "A", b: "B", c: "C", d: "D" }

function getOptText(q: QuizQuestion, opt: string): string {
    return ({ a: q.option_a, b: q.option_b, c: q.option_c, d: q.option_d } as Record<string, string>)[opt] ?? ""
}

function OnboardingQuizPanel({ planId }: { planId: number }) {
    const [view, setView] = useState<QuizView>("loading")
    const [questions, setQuestions] = useState<QuizQuestion[]>([])
    const [attempts, setAttempts] = useState<QuizAttempt[]>([])
    const [selected, setSelected] = useState<Record<number, string>>({})
    const [submitting, setSubmitting] = useState(false)
    const [result, setResult] = useState<SubmitResult | null>(null)
    const { toast } = useToast()
    const { setSettingsOpen } = useStore((s: any) => s)

    useEffect(() => {
        const controller = new AbortController()
        loadQuiz(controller.signal)
        return () => controller.abort()
    }, [planId])

    async function loadQuiz(signal?: AbortSignal) {
        setView("loading")
        try {
            const res = await api.get(`/py/onboarding/${planId}/quiz`, signal ? { signal } : {})
            if (signal?.aborted) return
            setQuestions(res.data.questions ?? [])
            setAttempts(res.data.attempts ?? [])
            setView("ready")
        } catch (err: any) {
            if (signal?.aborted) return
            if (err?.response?.status === 404) setView("not_generated")
            else setView("error")
        }
    }

    async function handleGenerate() {
        setView("generating")
        try {
            await api.post(`/py/onboarding/${planId}/quiz/generate`)
        } catch (err: any) {
            const status = err?.response?.status
            const detail = err?.response?.data?.detail ?? ""
            if (status === 409) {
                // already generated — just load
            } else if (status === 400 && (detail.includes("LLM") || detail.includes("provider"))) {
                toast({
                    title: "LLM not configured",
                    description: "Add your provider and API key in Settings.",
                    action: <ToastAction altText="Open Settings" onClick={() => setSettingsOpen(true)}>Open Settings</ToastAction>,
                })
                setView("not_generated")
                return
            } else {
                toast({ variant: "destructive", title: "Error", description: detail || "Failed to generate quiz." })
                setView("generate_error")
                return
            }
        }
        await loadQuiz()
    }

    function startAttempt() {
        setResult(null)
        setSelected({})
        setView("taking")
    }

    async function handleSubmit() {
        // Grading is done server-side (the client no longer has the answer key). We
        // send the selected answers and use the attempt response for score + results.
        const submittedAnswers: Record<string, string> = {}
        questions.forEach((_q, i) => { submittedAnswers[String(i)] = selected[i] ?? "" })
        setSubmitting(true)
        try {
            const { success, data } = await postRequest(`/py/onboarding/${planId}/quiz/attempt`, { answers: submittedAnswers })
            if (success && data?.results) {
                setAttempts(prev => [data.attempt, ...prev])
                setResult({ score: data.score, passed: data.score >= PASS_SCORE, results: data.results })
                setView("submitted")
            } else {
                toast({ variant: "destructive", title: "Error", description: "Could not submit quiz. Please try again." })
            }
        } catch {
            toast({ variant: "destructive", title: "Error", description: "Could not submit quiz. Please try again." })
        }
        setSubmitting(false)
    }

    if (view === "loading") return (
        <div className="flex items-center justify-center h-full">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
    )

    if (view === "error") return (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
            <p className="text-sm text-muted-foreground">Could not load quiz. Please try again.</p>
            <Button variant="outline" size="sm" onClick={() => loadQuiz()}>Retry</Button>
        </div>
    )

    if (view === "generate_error") return (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
            <p className="text-sm text-muted-foreground">Quiz generation failed. Please try again.</p>
            <Button variant="outline" size="sm" onClick={handleGenerate}>Try Again</Button>
        </div>
    )

    if (view === "not_generated" || view === "generating") return (
        <div className="flex flex-col h-full overflow-y-auto">
            <div className="mx-auto w-full max-w-xl px-6 py-10 space-y-8">
                <div className="space-y-3">
                    <div className="flex items-center gap-2">
                        <GraduationCap className="h-5 w-5 text-primary" />
                        <h2 className="text-xl font-bold tracking-tight">Final Quiz</h2>
                    </div>
                    <p className="text-sm text-muted-foreground">A 10-question quiz grounded in your company's docs, covering all 7 days of your onboarding plan.</p>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                        <p className="text-2xl font-bold">10</p>
                        <p className="text-xs text-muted-foreground mt-0.5">Questions</p>
                    </div>
                    <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                        <p className="text-2xl font-bold">{PASS_SCORE}%</p>
                        <p className="text-xs text-muted-foreground mt-0.5">Pass Score</p>
                    </div>
                </div>
                <Button className="w-full h-11 rounded-xl" onClick={handleGenerate} disabled={view === "generating"}>
                    {view === "generating"
                        ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating…</>
                        : <><Sparkles className="h-4 w-4 mr-2" />Generate Final Quiz</>
                    }
                </Button>
            </div>
        </div>
    )

    if (view === "ready") {
        const hasPrev = attempts.length > 0
        const bestScore = hasPrev ? Math.max(...attempts.map(a => a.score)) : null
        const passed = bestScore !== null && bestScore >= PASS_SCORE
        return (
            <div className="flex flex-col h-full overflow-y-auto">
                <div className="mx-auto w-full max-w-xl px-6 py-10 space-y-8">
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <GraduationCap className="h-5 w-5 text-primary" />
                            <h2 className="text-xl font-bold tracking-tight">Final Quiz</h2>
                            {passed && (
                                <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 ml-auto">
                                    <CheckCircle2 className="h-3.5 w-3.5" /> Passed
                                </span>
                            )}
                        </div>
                        <p className="text-sm text-muted-foreground">Test your knowledge across all 7 onboarding days. You need {PASS_SCORE}% to pass.</p>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{questions.length}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Questions</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{PASS_SCORE}%</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Pass Score</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{attempts.length}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Attempt{attempts.length !== 1 ? "s" : ""}</p>
                        </div>
                    </div>
                    {hasPrev && bestScore !== null && (
                        <div className="rounded-xl border bg-card px-5 py-4 space-y-3">
                            <div className="flex items-center justify-between text-sm">
                                <span className="font-medium">Your best score</span>
                                <span className={cn("font-bold", passed ? "text-emerald-600" : "text-foreground")}>{bestScore}%</span>
                            </div>
                            <div className="relative h-2.5 bg-muted rounded-full overflow-hidden">
                                <div className="absolute top-0 bottom-0 w-0.5 bg-foreground/30 z-10" style={{ left: `${PASS_SCORE}%` }} />
                                <div className={cn("h-full rounded-full transition-all duration-500", passed ? "bg-emerald-500" : "bg-primary")} style={{ width: `${bestScore}%` }} />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>0%</span>
                                <span className="text-foreground/50">Pass: {PASS_SCORE}%</span>
                                <span>100%</span>
                            </div>
                        </div>
                    )}
                    <Button className="w-full h-11 rounded-xl" onClick={startAttempt}>
                        <GraduationCap className="h-4 w-4 mr-2" />
                        {hasPrev ? "Retake Quiz" : "Start Quiz"}
                    </Button>
                </div>
            </div>
        )
    }

    if (view === "taking") {
        const answered = Object.keys(selected).length
        const total = questions.length
        return (
            <div className="flex flex-col h-full overflow-hidden">
                <div className="border-b px-4 sm:px-8 py-4 bg-background shrink-0 space-y-2">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <GraduationCap className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Final Quiz</h2>
                        </div>
                        <span className="text-xs text-muted-foreground">{answered}/{total} answered</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-primary rounded-full transition-all duration-300" style={{ width: `${total > 0 ? (answered / total) * 100 : 0}%` }} />
                    </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-6">
                        {questions.map((q, i) => (
                            <div key={i} className="rounded-xl border bg-card p-5 space-y-3">
                                <p className="text-sm font-medium text-foreground">
                                    <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>{q.question}
                                </p>
                                <div className="grid grid-cols-1 gap-2">
                                    {QUIZ_OPTS.map((opt) => {
                                        const text = getOptText(q, opt)
                                        const isSel = selected[i] === opt
                                        return (
                                            <button key={opt} type="button"
                                                onClick={() => setSelected(prev => ({ ...prev, [i]: opt }))}
                                                className={cn(
                                                    "flex items-center gap-3 px-4 py-2.5 rounded-xl border text-sm text-left transition-all duration-150",
                                                    isSel ? "border-primary bg-primary/10 text-primary font-medium" : "border-border hover:border-primary/50 hover:bg-muted text-foreground"
                                                )}
                                            >
                                                <span className={cn(
                                                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-mono font-semibold transition-colors",
                                                    isSel ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40 text-muted-foreground"
                                                )}>{OPT_LABELS[opt]}</span>
                                                <span>{text}</span>
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>
                        ))}
                        <div className="pb-8">
                            <Button className="w-full h-11 rounded-xl" disabled={submitting || answered < total} onClick={handleSubmit}>
                                {submitting
                                    ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Submitting…</>
                                    : <><GraduationCap className="h-4 w-4 mr-2" />Submit Quiz</>
                                }
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    if (view === "submitted" && result) {
        return (
            <div className="flex flex-col h-full overflow-hidden">
                <div className={cn("border-b px-4 sm:px-8 py-5 shrink-0", result.passed ? "bg-emerald-50 dark:bg-emerald-950/20" : "bg-red-50 dark:bg-red-950/20")}>
                    <div className="flex items-center gap-4">
                        {result.passed
                            ? <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
                            : <XCircle className="h-8 w-8 text-red-500 shrink-0" />
                        }
                        <div className="flex-1 min-w-0">
                            <h2 className={cn("text-lg font-bold", result.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>
                                {result.passed ? "Quiz Passed!" : "Not Quite"}
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                Score: <span className="font-semibold text-foreground">{result.score}%</span>
                                {" · "}{result.passed ? "Onboarding complete!" : `Need ${PASS_SCORE}% to pass`}
                            </p>
                        </div>
                        <p className={cn("text-3xl font-black shrink-0", result.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                            {result.score}%
                        </p>
                    </div>
                    <div className="flex gap-2 mt-4">
                        <Button variant="outline" size="sm" onClick={() => setView("ready")}>Quiz Overview</Button>
                        <Button size="sm" onClick={startAttempt}><RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Retry Quiz</Button>
                    </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-4">
                        {questions.map((q, i) => {
                            const r = result.results[i]
                            if (!r) return null
                            return (
                                <div key={i} className={cn("rounded-xl border p-4 space-y-3", r.is_correct ? "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20" : "border-red-200 bg-red-50/50 dark:bg-red-950/20")}>
                                    <div className="flex items-start gap-2">
                                        {r.is_correct ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" /> : <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />}
                                        <p className="text-sm font-medium text-foreground flex-1 min-w-0">
                                            <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>{q.question}
                                        </p>
                                    </div>
                                    <div className="grid grid-cols-1 gap-1.5 pl-6">
                                        {QUIZ_OPTS.map((opt) => {
                                            const text = getOptText(q, opt)
                                            const isCorrect = opt === r.correct
                                            const isSelectedWrong = opt === r.selected && !r.is_correct
                                            return (
                                                <div key={opt} className={cn(
                                                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border",
                                                    isCorrect ? "border-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 font-medium text-emerald-800 dark:text-emerald-300"
                                                        : isSelectedWrong ? "border-red-300 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                                                        : "border-transparent text-muted-foreground"
                                                )}>
                                                    <span className="font-mono text-xs w-4 shrink-0">{OPT_LABELS[opt]}.</span>
                                                    <span>{text}</span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                    {q.explanation && <p className="pl-6 text-xs text-muted-foreground italic">{q.explanation}</p>}
                                </div>
                            )
                        })}
                    </div>
                </div>
            </div>
        )
    }

    return null
}

// ─── Day Nav (left panel) ─────────────────────────────────────────────────────

function DayNav({
    plan, days, activeDayId, onSelectDay, isQuizActive, onSelectQuiz,
    completedCount, shareEnabled, togglingShare, copied, copyFailed,
    onToggleShare, onCopyLink, bulkGenerating, onGenerateAll,
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
    bulkGenerating: { done: number; total: number } | null
    onGenerateAll: () => void
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
                {(() => {
                    const pendingCount = days.filter(d => !d.content_blocks).length
                    if (bulkGenerating) return (
                        <div className="flex items-center gap-2 px-4 py-2 border-b">
                            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/60" />
                            <span className="text-xs text-muted-foreground/60">{bulkGenerating.done}/{bulkGenerating.total} generated</span>
                        </div>
                    )
                    if (pendingCount === 0) return null
                    return (
                        <div className="px-4 py-2 border-b">
                            <button
                                type="button"
                                onClick={onGenerateAll}
                                className="flex items-center gap-1 text-xs text-muted-foreground/70 hover:text-primary border border-muted-foreground/20 hover:border-primary/40 rounded px-1.5 py-0.5 transition-colors"
                            >
                                <Zap className="h-2.5 w-2.5" />
                                Generate all
                            </button>
                        </div>
                    )
                })()}
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
    const [bulkGenerating, setBulkGenerating] = useState<{ done: number; total: number } | null>(null)
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
    const { toast } = useToast()

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

    async function handleGenerateAll() {
        if (!plan) return
        const todo = days.filter(d => !d.content_blocks)
        if (todo.length === 0) return
        setBulkGenerating({ done: 0, total: todo.length })
        for (let i = 0; i < todo.length; i++) {
            const day = todo[i]
            setGeneratingIds(prev => new Set(prev).add(day.id))
            try {
                const response = await api.get(`/py/onboarding/${plan.id}/day/${day.day}`)
                if (response.data?.day?.content_blocks) handleContentGenerated(day.id)
            } catch (err: any) {
                const detail = err?.response?.data?.detail
                toast({ variant: "destructive", title: `Failed: Day ${day.day}`, description: typeof detail === "string" ? detail : undefined })
            } finally {
                setGeneratingIds(prev => { const next = new Set(prev); next.delete(day.id); return next })
                setBulkGenerating({ done: i + 1, total: todo.length })
            }
        }
        setBulkGenerating(null)
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
                        bulkGenerating={bulkGenerating}
                        onGenerateAll={handleGenerateAll}
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
