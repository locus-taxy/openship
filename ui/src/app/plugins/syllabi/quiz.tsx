import { useEffect, useState } from "react"

function fisherYates<T>(arr: T[]): T[] {
    const a = [...arr]
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]]
    }
    return a
}
import { CheckCircle2, XCircle, Loader2, BookCheck, RotateCcw, Sparkles, Brain } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import api, { postRequest } from "@/services"

interface QuizQuestion {
    id: number
    position: number
    question: string
    option_a: string
    option_b: string
    option_c: string
    option_d: string
}

interface QuizData {
    quiz_id: number
    skill_id: number
    pass_score: number
    status: string
    questions: QuizQuestion[]
    best_score: number | null
    attempt_count: number
}

interface QuestionResult {
    question_id: number
    topic?: string
    selected: string
    correct: string
    is_correct: boolean
    explanation: string
}

interface SubmitResult {
    attempt_id: number
    score: number
    passed: boolean
    pass_score: number
    results: QuestionResult[]
    topic_scores: Record<string, TopicScore>
}

interface TopicScore {
    correct: number
    total: number
    pct: number
}

interface LatestAttemptData {
    attempt_id: number
    score: number
    passed: boolean
    pass_score: number
    created_at: string | null
    results: (QuestionResult & { topic: string })[]
    topic_scores: Record<string, TopicScore>
}

const OPTIONS = ["A", "B", "C", "D"] as const

function getOptionText(q: QuizQuestion, opt: string): string {
    return ({ A: q.option_a, B: q.option_b, C: q.option_c, D: q.option_d } as Record<string, string>)[opt] ?? ""
}

type View = "loading" | "not_generated" | "generating" | "ready" | "taking" | "submitted" | "last_results" | "error" | "generate_error"

export function QuizPanel({
    skillId,
    onBack,
    onQuizStatusChange,
    hasAllWeeklyData = false,
}: {
    skillId: string | number
    onBack: () => void
    onQuizStatusChange?: (status: string) => void
    hasAllWeeklyData?: boolean
}) {
    const [view, setView] = useState<View>("loading")
    const [quiz, setQuiz] = useState<QuizData | null>(null)
    const [submitError, setSubmitError] = useState("")
    const [answers, setAnswers] = useState<Record<number, string>>({})
    const [submitting, setSubmitting] = useState(false)
    const [result, setResult] = useState<SubmitResult | null>(null)
    const [lastAttempt, setLastAttempt] = useState<LatestAttemptData | null>(null)
    const [loadingLastAttempt, setLoadingLastAttempt] = useState(false)

    useEffect(() => {
        const controller = new AbortController()
        loadQuiz(controller.signal)
        return () => controller.abort()
    }, [skillId])

    async function loadQuiz(signal?: AbortSignal) {
        setView("loading")
        try {
            const res = await api.get(`/py/quiz/${skillId}`, signal ? { signal } : {})
            if (signal?.aborted) return
            setQuiz(res.data)
            setView("ready")
            onQuizStatusChange?.(res.data.status === "passed" ? "passed" : "available")
        } catch (err: any) {
            if (signal?.aborted) return
            if (err?.response?.status === 404) {
                setView("not_generated")
            } else {
                setView("error")
            }
        }
    }

    async function handleGenerate() {
        setView("generating")
        try {
            await api.post(`/py/quiz/${skillId}/generate`)
        } catch (err: any) {
            if (err?.response?.status !== 409) { setView("generate_error"); return }
        }
        await loadQuiz()
    }

    async function handleRegenerate() {
        setView("generating")
        try { await api.delete(`/py/quiz/${skillId}/final`) } catch { /* ignore */ }
        try {
            await api.post(`/py/quiz/${skillId}/generate`)
        } catch (err: any) {
            if (err?.response?.status !== 409) { setView("generate_error"); return }
        }
        await loadQuiz()
    }

    async function handleSubmit() {
        if (!quiz) return
        const unanswered = quiz.questions.filter((q) => !answers[q.id])
        if (unanswered.length > 0) {
            setSubmitError(`Please answer all questions (${unanswered.length} remaining).`)
            return
        }
        setSubmitError("")
        setSubmitting(true)
        const { success, data } = await postRequest(`/py/quiz/${skillId}/submit`, { answers })
        if (success) {
            setResult(data)
            setView("submitted")
            if (data.passed) onQuizStatusChange?.("passed")
        } else {
            setSubmitError(data?.detail ?? "Submission failed. Please try again.")
        }
        setSubmitting(false)
    }

    async function loadLastAttempt() {
        setLoadingLastAttempt(true)
        try {
            const res = await api.get(`/py/quiz/${skillId}/attempts/latest`)
            setLastAttempt(res.data)
            setView("last_results")
        } catch {
            // ignore — button only shown when attempts exist
        } finally {
            setLoadingLastAttempt(false)
        }
    }

    function startAttempt() {
        if (quiz) {
            const shuffled = fisherYates(quiz.questions)
            setQuiz({ ...quiz, questions: shuffled })
        }
        setResult(null)
        setAnswers({})
        setSubmitError("")
        setView("taking")
    }

    function handleRetry() {
        startAttempt()
    }

    // ── Loading ──────────────────────────────────────────────────────────────

    if (view === "loading") {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        )
    }

    if (view === "error") {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
                <p className="text-sm text-muted-foreground">Could not load quiz. Please try again.</p>
                <Button variant="outline" size="sm" onClick={() => loadQuiz()}>Retry</Button>
            </div>
        )
    }

    if (view === "generate_error") {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
                <p className="text-sm text-muted-foreground">Quiz generation failed — the AI returned fewer questions than expected. Please try again.</p>
                <Button variant="outline" size="sm" onClick={handleGenerate}>Try Again</Button>
            </div>
        )
    }

    if (view === "not_generated" || view === "generating") {
        return (
            <div className="flex flex-col h-full overflow-y-auto">
                <div className="mx-auto w-full max-w-xl px-6 py-10 space-y-8">
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <BookCheck className="h-5 w-5 text-primary" />
                            <h2 className="text-xl font-bold tracking-tight">Final Quiz</h2>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            ML-personalised test covering your weakest topics, shaped by your weekly quiz performance.
                        </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">70%</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Pass Score</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <Brain className="h-6 w-6 text-primary mx-auto mb-1" />
                            <p className="text-xs text-muted-foreground">ML Personalised</p>
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
    }

    if (view === "ready" && quiz) {
        const hasPrevAttempts = quiz.attempt_count > 0
        const passed = quiz.status === "passed"
        const bestScore = quiz.best_score ?? 0

        return (
            <div className="flex flex-col h-full overflow-y-auto">
                <div className="mx-auto w-full max-w-xl px-6 py-10 space-y-8">

                    {/* Header */}
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <BookCheck className="h-5 w-5 text-primary" />
                            <h2 className="text-xl font-bold tracking-tight">Final Quiz</h2>
                            {passed && (
                                <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 ml-auto">
                                    <CheckCircle2 className="h-3.5 w-3.5" /> Passed
                                </span>
                            )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                            Test your knowledge across all course topics. You need {quiz.pass_score}% to pass.
                        </p>
                    </div>

                    {/* Stats row */}
                    <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{quiz.questions.length}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Questions</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{quiz.pass_score}%</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Pass Score</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{quiz.attempt_count}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Attempt{quiz.attempt_count !== 1 ? "s" : ""}</p>
                        </div>
                    </div>

                    {/* Best score bar — only shown after at least one attempt */}
                    {hasPrevAttempts && (
                        <div className="rounded-xl border bg-card px-5 py-4 space-y-3">
                            <div className="flex items-center justify-between text-sm">
                                <span className="font-medium">Your best score</span>
                                <span className={cn(
                                    "font-bold",
                                    passed ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"
                                )}>
                                    {bestScore}%
                                </span>
                            </div>
                            <div className="relative h-2.5 bg-muted rounded-full overflow-hidden">
                                {/* pass threshold marker */}
                                <div
                                    className="absolute top-0 bottom-0 w-0.5 bg-foreground/30 z-10"
                                    style={{ left: `${quiz.pass_score}%` }}
                                />
                                {/* score fill */}
                                <div
                                    className={cn(
                                        "h-full rounded-full transition-all duration-500",
                                        passed ? "bg-emerald-500" : bestScore >= quiz.pass_score ? "bg-emerald-500" : "bg-primary"
                                    )}
                                    style={{ width: `${bestScore}%` }}
                                />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>0%</span>
                                <span className="text-foreground/50">Pass: {quiz.pass_score}%</span>
                                <span>100%</span>
                            </div>
                        </div>
                    )}

                    {/* CTA */}
                    <div className="space-y-2">
                        <Button className="w-full h-11 rounded-xl" onClick={startAttempt}>
                            <BookCheck className="h-4 w-4 mr-2" />
                            {hasPrevAttempts ? "Retake Quiz" : "Start Quiz"}
                        </Button>
                        {hasPrevAttempts && (
                            <Button
                                variant="outline"
                                className="w-full h-10 rounded-xl"
                                onClick={loadLastAttempt}
                                disabled={loadingLastAttempt}
                            >
                                {loadingLastAttempt
                                    ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    : <BookCheck className="h-4 w-4 mr-2" />
                                }
                                View Last Results
                            </Button>
                        )}
                    </div>

                    {hasAllWeeklyData && (
                        <button
                            className="w-full text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center justify-center gap-1.5 py-1"
                            onClick={handleRegenerate}
                        >
                            <RotateCcw className="h-3 w-3" />
                            Regenerate with fresh ML data
                        </button>
                    )}
                </div>
            </div>
        )
    }

    // ── Last Results ─────────────────────────────────────────────────────────

    if (view === "last_results" && lastAttempt && quiz) {
        const resultMap = Object.fromEntries(lastAttempt.results.map((r) => [r.question_id, r]))
        const sortedTopics = Object.entries(lastAttempt.topic_scores).sort((a, b) => a[1].pct - b[1].pct)

        return (
            <div className="flex flex-col h-full overflow-hidden">
                <div className={cn(
                    "border-b px-4 sm:px-8 py-5 shrink-0",
                    lastAttempt.passed ? "bg-emerald-50 dark:bg-emerald-950/20" : "bg-red-50 dark:bg-red-950/20"
                )}>
                    <div className="flex items-center gap-4">
                        {lastAttempt.passed
                            ? <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
                            : <XCircle className="h-8 w-8 text-red-500 shrink-0" />
                        }
                        <div className="flex-1 min-w-0">
                            <h2 className={cn("text-lg font-bold", lastAttempt.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>
                                Last Attempt {lastAttempt.passed ? "— Passed" : "— Not Passed"}
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                Score: <span className="font-semibold text-foreground">{lastAttempt.score}%</span>
                                {lastAttempt.created_at && (
                                    <> · {new Date(lastAttempt.created_at).toLocaleDateString()}</>
                                )}
                            </p>
                        </div>
                        <p className={cn("text-3xl font-black shrink-0", lastAttempt.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                            {lastAttempt.score}%
                        </p>
                    </div>
                    <div className="flex gap-2 mt-4">
                        <Button variant="outline" size="sm" onClick={() => setView("ready")}>Quiz Overview</Button>
                        <Button size="sm" onClick={startAttempt}>
                            <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Retake
                        </Button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-6">
                        {/* Topic breakdown */}
                        {sortedTopics.length > 1 && (
                            <div className="rounded-xl border bg-card p-4 space-y-3">
                                <h3 className="text-sm font-semibold">Score by Topic</h3>
                                <div className="space-y-2">
                                    {sortedTopics.map(([topic, ts]) => (
                                        <div key={topic} className="space-y-1">
                                            <div className="flex justify-between text-xs">
                                                <span className="text-muted-foreground truncate pr-2">{topic}</span>
                                                <span className={cn("font-semibold shrink-0", ts.pct >= 70 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                                                    {ts.correct}/{ts.total} · {ts.pct}%
                                                </span>
                                            </div>
                                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className={cn("h-full rounded-full", ts.pct >= 70 ? "bg-emerald-500" : "bg-red-400")}
                                                    style={{ width: `${ts.pct}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Per-question breakdown */}
                        {quiz.questions.map((q, i) => {
                            const r = resultMap[q.id]
                            if (!r) return null
                            return (
                                <div key={q.id} className={cn(
                                    "rounded-xl border p-4 space-y-3",
                                    r.is_correct ? "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20" : "border-red-200 bg-red-50/50 dark:bg-red-950/20"
                                )}>
                                    <div className="flex items-start gap-2">
                                        {r.is_correct
                                            ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                                            : <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                                        }
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-foreground">
                                                <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                                {q.question}
                                            </p>
                                            {r.topic && r.topic !== "General" && (
                                                <span className="mt-1 inline-block text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5">{r.topic}</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 gap-1.5 pl-6">
                                        {OPTIONS.map((opt) => {
                                            const text = getOptionText(q, opt)
                                            const isCorrect = opt === r.correct
                                            const isSelected = opt === r.selected
                                            return (
                                                <div key={opt} className={cn(
                                                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border",
                                                    isCorrect
                                                        ? "border-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 font-medium text-emerald-800 dark:text-emerald-300"
                                                        : isSelected && !isCorrect
                                                            ? "border-red-300 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                                                            : "border-transparent text-muted-foreground"
                                                )}>
                                                    <span className="font-mono text-xs w-4 shrink-0">{opt}.</span>
                                                    <span>{text}</span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                    <p className="pl-6 text-xs text-muted-foreground italic">{r.explanation}</p>
                                </div>
                            )
                        })}
                    </div>
                </div>
            </div>
        )
    }

    // ── Taking ───────────────────────────────────────────────────────────────

    if (view === "taking" && quiz) {
        const answeredCount = Object.keys(answers).length
        const totalCount = quiz.questions.length

        return (
            <div className="flex flex-col h-full overflow-hidden">
                {/* Sticky header */}
                <div className="border-b px-4 sm:px-8 py-4 bg-background shrink-0 space-y-2">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <BookCheck className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Final Quiz</h2>
                        </div>
                        <span className="text-xs text-muted-foreground">{answeredCount}/{totalCount} answered</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                            className="h-full bg-primary rounded-full transition-all duration-300"
                            style={{ width: `${totalCount > 0 ? (answeredCount / totalCount) * 100 : 0}%` }}
                        />
                    </div>
                </div>

                {/* Questions */}
                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-6">
                        {quiz.questions.map((q, i) => (
                            <div key={q.id} className="rounded-xl border bg-card p-5 space-y-3">
                                <p className="text-sm font-medium text-foreground">
                                    <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                    {q.question}
                                </p>
                                <div className="grid grid-cols-1 gap-2">
                                    {OPTIONS.map((opt) => {
                                        const text = getOptionText(q, opt)
                                        const selected = answers[q.id] === opt
                                        return (
                                            <button
                                                key={opt}
                                                type="button"
                                                onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                                                className={cn(
                                                    "flex items-center gap-3 px-4 py-2.5 rounded-xl border text-sm text-left transition-all duration-150",
                                                    selected
                                                        ? "border-primary bg-primary/10 text-primary font-medium"
                                                        : "border-border hover:border-primary/50 hover:bg-muted text-foreground"
                                                )}
                                            >
                                                <span className={cn(
                                                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-mono font-semibold transition-colors",
                                                    selected ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40 text-muted-foreground"
                                                )}>
                                                    {opt}
                                                </span>
                                                <span>{text}</span>
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>
                        ))}

                        {submitError && <p className="text-sm text-destructive">{submitError}</p>}

                        <div className="pb-8">
                            <Button
                                className="w-full h-11 rounded-xl"
                                disabled={submitting}
                                onClick={handleSubmit}
                            >
                                {submitting
                                    ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Submitting…</>
                                    : <><BookCheck className="h-4 w-4 mr-2" />Submit Quiz</>
                                }
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    // ── Submitted (results) ──────────────────────────────────────────────────

    if (view === "submitted" && result && quiz) {
        const resultMap = Object.fromEntries(result.results.map((r) => [r.question_id, r]))
        const sortedTopics = Object.entries(result.topic_scores ?? {}).sort((a, b) => a[1].pct - b[1].pct)

        return (
            <div className="flex flex-col h-full overflow-hidden">
                {/* Sticky score card */}
                <div className={cn(
                    "border-b px-4 sm:px-8 py-5 shrink-0",
                    result.passed ? "bg-emerald-50 dark:bg-emerald-950/20" : "bg-red-50 dark:bg-red-950/20"
                )}>
                    <div className="flex items-center gap-4">
                        {result.passed
                            ? <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
                            : <XCircle className="h-8 w-8 text-red-500 shrink-0" />
                        }
                        <div className="flex-1 min-w-0">
                            <h2 className={cn(
                                "text-lg font-bold",
                                result.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"
                            )}>
                                {result.passed ? "Quiz Passed!" : "Not Quite"}
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                Score: <span className="font-semibold text-foreground">{result.score}%</span>
                                {" · "}
                                {result.passed
                                    ? "You've completed this course!"
                                    : `Need ${result.pass_score}% to pass`}
                            </p>
                        </div>
                        <p className={cn(
                            "text-3xl font-black shrink-0",
                            result.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                        )}>
                            {result.score}%
                        </p>
                    </div>
                    <div className="flex gap-2 mt-4">
                        <Button variant="outline" size="sm" onClick={() => loadQuiz()}>
                            Quiz Overview
                        </Button>
                        <Button size="sm" onClick={handleRetry}>
                            <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Retry Quiz
                        </Button>
                    </div>
                </div>

                {/* Per-question breakdown */}
                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-4">
                        {/* Topic breakdown */}
                        {sortedTopics.length > 1 && (
                            <div className="rounded-xl border bg-card p-4 space-y-3">
                                <h3 className="text-sm font-semibold">Score by Topic</h3>
                                <div className="space-y-2">
                                    {sortedTopics.map(([topic, ts]) => (
                                        <div key={topic} className="space-y-1">
                                            <div className="flex justify-between text-xs">
                                                <span className="text-muted-foreground truncate pr-2">{topic}</span>
                                                <span className={cn("font-semibold shrink-0", ts.pct >= 70 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                                                    {ts.correct}/{ts.total} · {ts.pct}%
                                                </span>
                                            </div>
                                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className={cn("h-full rounded-full", ts.pct >= 70 ? "bg-emerald-500" : "bg-red-400")}
                                                    style={{ width: `${ts.pct}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {quiz.questions.map((q, i) => {
                            const r = resultMap[q.id]
                            if (!r) return null
                            return (
                                <div key={q.id} className={cn(
                                    "rounded-xl border p-4 space-y-3",
                                    r.is_correct
                                        ? "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20"
                                        : "border-red-200 bg-red-50/50 dark:bg-red-950/20"
                                )}>
                                    <div className="flex items-start gap-2">
                                        {r.is_correct
                                            ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                                            : <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                                        }
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-foreground">
                                                <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                                {q.question}
                                            </p>
                                            {r.topic && r.topic !== "General" && (
                                                <span className="mt-1 inline-block text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5">{r.topic}</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 gap-1.5 pl-6">
                                        {OPTIONS.map((opt) => {
                                            const text = getOptionText(q, opt)
                                            const isCorrect = opt === r.correct
                                            const isSelected = opt === r.selected
                                            return (
                                                <div key={opt} className={cn(
                                                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border",
                                                    isCorrect
                                                        ? "border-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 font-medium text-emerald-800 dark:text-emerald-300"
                                                        : isSelected && !isCorrect
                                                            ? "border-red-300 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                                                            : "border-transparent text-muted-foreground"
                                                )}>
                                                    <span className="font-mono text-xs w-4 shrink-0">{opt}.</span>
                                                    <span>{text}</span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                    <p className="pl-6 text-xs text-muted-foreground italic">{r.explanation}</p>
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

// ── Weekly Quiz ───────────────────────────────────────────────────────────────

interface WeeklySubmitResult {
    attempt_id: number
    score: number
    passed: boolean
    pass_score: number
    results: QuestionResult[]
    topic_scores: Record<string, TopicScore>
    next_week_style: string | null
    next_week_unlocked: number | null
}

const STYLE_INFO: Record<string, { label: string; description: string }> = {
    visual_heavy:  { label: "Visual-Heavy",   description: "Diagrams, charts, and visual aids to reinforce concepts" },
    example_heavy: { label: "Example-Heavy",  description: "Learning through hands-on examples and exercises" },
    diagram_heavy: { label: "Diagram-Heavy",  description: "Flowcharts and structured diagrams to map relationships" },
    story_driven:  { label: "Story-Driven",   description: "Concepts introduced through real-world narratives and scenarios" },
}

type WeeklyView = "loading" | "not_generated" | "generating" | "ready" | "taking" | "submitted" | "last_results" | "error"

export function WeeklyQuizPanel({
    skillId,
    week,
    onBack,
    onQuizStatusChange,
    onWeekUnlocked,
}: {
    skillId: string | number
    week: number
    onBack: () => void
    onQuizStatusChange?: (status: string) => void
    onWeekUnlocked?: (newGeneratedWeeks: number) => void
}) {
    const [view, setView] = useState<WeeklyView>("loading")
    const [quiz, setQuiz] = useState<QuizData | null>(null)
    const [answers, setAnswers] = useState<Record<number, string>>({})
    const [submitting, setSubmitting] = useState(false)
    const [submitError, setSubmitError] = useState("")
    const [result, setResult] = useState<WeeklySubmitResult | null>(null)
    const [generateError, setGenerateError] = useState("")
    const [lastAttempt, setLastAttempt] = useState<LatestAttemptData | null>(null)
    const [loadingLastAttempt, setLoadingLastAttempt] = useState(false)

    useEffect(() => {
        const controller = new AbortController()
        loadQuiz(controller.signal)
        return () => controller.abort()
    }, [skillId, week])

    async function loadQuiz(signal?: AbortSignal) {
        setView("loading")
        try {
            const res = await api.get(`/py/quiz/${skillId}/week/${week}`, { signal })
            if (signal?.aborted) return
            setQuiz(res.data)
            setView("ready")
            onQuizStatusChange?.(res.data.status === "passed" ? "passed" : "available")
        } catch (err: any) {
            if (signal?.aborted || err?.code === "ERR_CANCELED") return
            if (err?.response?.status === 404) {
                setView("not_generated")
            } else {
                setView("error")
            }
        }
    }

    async function handleGenerate() {
        setGenerateError("")
        setView("generating")
        try {
            await api.post(`/py/quiz/${skillId}/week/${week}/generate`, undefined, { timeout: 120000 })
            await loadQuiz()
        } catch (err: any) {
            const status = err?.response?.status
            if (status === 409) {
                await loadQuiz()
            } else {
                const msg = err?.response?.data?.detail ?? "Quiz generation failed. Please try again."
                setGenerateError(msg)
                setView("not_generated")
            }
        }
    }

    async function handleSubmit() {
        if (!quiz) return
        const unanswered = quiz.questions.filter((q) => !answers[q.id])
        if (unanswered.length > 0) {
            setSubmitError(`Please answer all questions (${unanswered.length} remaining).`)
            return
        }
        setSubmitError("")
        setSubmitting(true)
        const { success, data } = await postRequest(`/py/quiz/${skillId}/week/${week}/submit`, { answers })
        if (success) {
            setResult(data)
            setView("submitted")
            onQuizStatusChange?.(data.passed ? "passed" : "available")
            if (data.next_week_unlocked != null) {
                onWeekUnlocked?.(data.next_week_unlocked)
            }
        } else {
            setSubmitError(data?.detail ?? "Submission failed. Please try again.")
        }
        setSubmitting(false)
    }

    async function loadLastAttemptWeekly() {
        setLoadingLastAttempt(true)
        try {
            const res = await api.get(`/py/quiz/${skillId}/week/${week}/attempts/latest`)
            setLastAttempt(res.data)
            setView("last_results")
        } catch {
            // ignore
        } finally {
            setLoadingLastAttempt(false)
        }
    }

    function startAttempt() {
        if (quiz) {
            const shuffled = fisherYates(quiz.questions)
            setQuiz({ ...quiz, questions: shuffled })
        }
        setResult(null)
        setAnswers({})
        setSubmitError("")
        setView("taking")
    }

    // ── Loading ──────────────────────────────────────────────────────────────

    if (view === "loading") {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        )
    }

    if (view === "error") {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-6">
                <p className="text-sm text-muted-foreground">Could not load quiz. Please try again.</p>
                <Button variant="outline" size="sm" onClick={() => loadQuiz()}>Retry</Button>
            </div>
        )
    }

    // ── Not generated ────────────────────────────────────────────────────────

    if (view === "not_generated" || view === "generating") {
        return (
            <div className="flex flex-col h-full overflow-y-auto">
                <div className="mx-auto w-full max-w-xl px-6 py-10 space-y-8">
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <Brain className="h-5 w-5 text-primary" />
                            <h2 className="text-xl font-bold tracking-tight">Week {week} Quiz</h2>
                        </div>
                        <p className="text-sm text-muted-foreground">
                            5 questions covering this week's topics. Your answers train the ML model to personalise your final quiz and content style.
                        </p>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">5</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Questions</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">60%</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Pass Score</p>
                        </div>
                    </div>
                    {generateError && (
                        <p className="text-sm text-destructive text-center">{generateError}</p>
                    )}
                    <Button className="w-full h-11 rounded-xl" onClick={handleGenerate} disabled={view === "generating"}>
                        {view === "generating"
                            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating…</>
                            : <><Sparkles className="h-4 w-4 mr-2" />Generate Week {week} Quiz</>
                        }
                    </Button>
                </div>
            </div>
        )
    }

    // ── Ready ────────────────────────────────────────────────────────────────

    if (view === "ready" && quiz) {
        const hasPrevAttempts = quiz.attempt_count > 0
        const passed = quiz.status === "passed"
        const bestScore = quiz.best_score ?? 0

        return (
            <div className="flex flex-col h-full overflow-y-auto">
                <div className="mx-auto w-full max-w-xl px-6 py-10 space-y-8">
                    <div className="space-y-3">
                        <div className="flex items-center gap-2">
                            <Brain className="h-5 w-5 text-primary" />
                            <h2 className="text-xl font-bold tracking-tight">Week {week} Quiz</h2>
                            {passed && (
                                <span className="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 ml-auto">
                                    <CheckCircle2 className="h-3.5 w-3.5" /> Passed
                                </span>
                            )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                            Test your knowledge of this week's topics. Your results feed into the ML model to personalise upcoming content.
                        </p>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{quiz.questions.length}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Questions</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{quiz.pass_score}%</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Pass Score</p>
                        </div>
                        <div className="rounded-xl border bg-muted/30 px-4 py-3 text-center">
                            <p className="text-2xl font-bold">{quiz.attempt_count}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">Attempt{quiz.attempt_count !== 1 ? "s" : ""}</p>
                        </div>
                    </div>

                    {hasPrevAttempts && (
                        <div className="rounded-xl border bg-card px-5 py-4 space-y-3">
                            <div className="flex items-center justify-between text-sm">
                                <span className="font-medium">Your best score</span>
                                <span className={cn("font-bold", passed ? "text-emerald-600 dark:text-emerald-400" : "text-foreground")}>
                                    {bestScore}%
                                </span>
                            </div>
                            <div className="relative h-2.5 bg-muted rounded-full overflow-hidden">
                                <div className="absolute top-0 bottom-0 w-0.5 bg-foreground/30 z-10" style={{ left: `${quiz.pass_score}%` }} />
                                <div
                                    className={cn("h-full rounded-full transition-all duration-500", passed || bestScore >= quiz.pass_score ? "bg-emerald-500" : "bg-primary")}
                                    style={{ width: `${bestScore}%` }}
                                />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span>0%</span>
                                <span className="text-foreground/50">Pass: {quiz.pass_score}%</span>
                                <span>100%</span>
                            </div>
                        </div>
                    )}

                    <div className="space-y-2">
                        <Button className="w-full h-11 rounded-xl" onClick={startAttempt}>
                            <Brain className="h-4 w-4 mr-2" />
                            {hasPrevAttempts ? "Retake Quiz" : "Start Quiz"}
                        </Button>
                        {hasPrevAttempts && (
                            <Button
                                variant="outline"
                                className="w-full h-10 rounded-xl"
                                onClick={loadLastAttemptWeekly}
                                disabled={loadingLastAttempt}
                            >
                                {loadingLastAttempt
                                    ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    : <Brain className="h-4 w-4 mr-2" />
                                }
                                View Last Results
                            </Button>
                        )}
                    </div>
                </div>
            </div>
        )
    }

    // ── Weekly Last Results ───────────────────────────────────────────────────

    if (view === "last_results" && lastAttempt && quiz) {
        const resultMap = Object.fromEntries(lastAttempt.results.map((r) => [r.question_id, r]))
        const sortedTopics = Object.entries(lastAttempt.topic_scores).sort((a, b) => a[1].pct - b[1].pct)

        return (
            <div className="flex flex-col h-full overflow-hidden">
                <div className={cn(
                    "border-b px-4 sm:px-8 py-5 shrink-0",
                    lastAttempt.passed ? "bg-emerald-50 dark:bg-emerald-950/20" : "bg-red-50 dark:bg-red-950/20"
                )}>
                    <div className="flex items-center gap-4">
                        {lastAttempt.passed
                            ? <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
                            : <XCircle className="h-8 w-8 text-red-500 shrink-0" />
                        }
                        <div className="flex-1 min-w-0">
                            <h2 className={cn("text-lg font-bold", lastAttempt.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>
                                Last Attempt — Week {week} {lastAttempt.passed ? "(Passed)" : "(Not Passed)"}
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                Score: <span className="font-semibold text-foreground">{lastAttempt.score}%</span>
                                {lastAttempt.created_at && (
                                    <> · {new Date(lastAttempt.created_at).toLocaleDateString()}</>
                                )}
                            </p>
                        </div>
                        <p className={cn("text-3xl font-black shrink-0", lastAttempt.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                            {lastAttempt.score}%
                        </p>
                    </div>
                    <div className="flex gap-2 mt-4">
                        <Button variant="outline" size="sm" onClick={() => setView("ready")}>Quiz Overview</Button>
                        <Button size="sm" onClick={startAttempt}>
                            <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Retry
                        </Button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-6">
                        {sortedTopics.length > 1 && (
                            <div className="rounded-xl border bg-card p-4 space-y-3">
                                <h3 className="text-sm font-semibold">Score by Topic</h3>
                                <div className="space-y-2">
                                    {sortedTopics.map(([topic, ts]) => (
                                        <div key={topic} className="space-y-1">
                                            <div className="flex justify-between text-xs">
                                                <span className="text-muted-foreground truncate pr-2">{topic}</span>
                                                <span className={cn("font-semibold shrink-0", ts.pct >= 60 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                                                    {ts.correct}/{ts.total} · {ts.pct}%
                                                </span>
                                            </div>
                                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className={cn("h-full rounded-full", ts.pct >= 60 ? "bg-emerald-500" : "bg-red-400")}
                                                    style={{ width: `${ts.pct}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {(() => {
                            const questionMap = Object.fromEntries(quiz.questions.map((q) => [q.id, q]))
                            return lastAttempt.results.map((r, i) => {
                                const q = questionMap[r.question_id]
                                if (!q) return null
                                return (
                                    <div key={r.question_id} className={cn(
                                        "rounded-xl border p-4 space-y-3",
                                        r.is_correct ? "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20" : "border-red-200 bg-red-50/50 dark:bg-red-950/20"
                                    )}>
                                        <div className="flex items-start gap-2">
                                            {r.is_correct
                                                ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                                                : <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                                            }
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-medium text-foreground">
                                                    <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                                    {q.question}
                                                </p>
                                                {r.topic && r.topic !== "General" && (
                                                    <span className="mt-1 inline-block text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5">{r.topic}</span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-1 gap-1.5 pl-6">
                                            {OPTIONS.map((opt) => {
                                                const text = getOptionText(q, opt)
                                                const isCorrect = opt === r.correct
                                                const isSelected = opt === r.selected
                                                return (
                                                    <div key={opt} className={cn(
                                                        "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border",
                                                        isCorrect
                                                            ? "border-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 font-medium text-emerald-800 dark:text-emerald-300"
                                                            : isSelected && !isCorrect
                                                                ? "border-red-300 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                                                                : "border-transparent text-muted-foreground"
                                                    )}>
                                                        <span className="font-mono text-xs w-4 shrink-0">{opt}.</span>
                                                        <span>{text}</span>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                        <p className="pl-6 text-xs text-muted-foreground italic">{r.explanation}</p>
                                    </div>
                                )
                            })
                        })()}
                    </div>
                </div>
            </div>
        )
    }

    // ── Taking ───────────────────────────────────────────────────────────────

    if (view === "taking" && quiz) {
        const answeredCount = Object.keys(answers).length
        const totalCount = quiz.questions.length

        return (
            <div className="flex flex-col h-full overflow-hidden">
                <div className="border-b px-4 sm:px-8 py-4 bg-background shrink-0 space-y-2">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Brain className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Week {week} Quiz</h2>
                        </div>
                        <span className="text-xs text-muted-foreground">{answeredCount}/{totalCount} answered</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                            className="h-full bg-primary rounded-full transition-all duration-300"
                            style={{ width: `${totalCount > 0 ? (answeredCount / totalCount) * 100 : 0}%` }}
                        />
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-6">
                        {quiz.questions.map((q, i) => (
                            <div key={q.id} className="rounded-xl border bg-card p-5 space-y-3">
                                <p className="text-sm font-medium text-foreground">
                                    <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                    {q.question}
                                </p>
                                <div className="grid grid-cols-1 gap-2">
                                    {OPTIONS.map((opt) => {
                                        const text = getOptionText(q, opt)
                                        const selected = answers[q.id] === opt
                                        return (
                                            <button
                                                key={opt}
                                                type="button"
                                                onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                                                className={cn(
                                                    "flex items-center gap-3 px-4 py-2.5 rounded-xl border text-sm text-left transition-all duration-150",
                                                    selected
                                                        ? "border-primary bg-primary/10 text-primary font-medium"
                                                        : "border-border hover:border-primary/50 hover:bg-muted text-foreground"
                                                )}
                                            >
                                                <span className={cn(
                                                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-mono font-semibold transition-colors",
                                                    selected ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40 text-muted-foreground"
                                                )}>
                                                    {opt}
                                                </span>
                                                <span>{text}</span>
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>
                        ))}

                        {submitError && <p className="text-sm text-destructive">{submitError}</p>}

                        <div className="pb-8">
                            <Button className="w-full h-11 rounded-xl" disabled={submitting} onClick={handleSubmit}>
                                {submitting
                                    ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Submitting…</>
                                    : <><Brain className="h-4 w-4 mr-2" />Submit Quiz</>
                                }
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    // ── Submitted ────────────────────────────────────────────────────────────

    if (view === "submitted" && result && quiz) {
        const resultMap = Object.fromEntries(result.results.map((r) => [r.question_id, r]))
        const styleInfo = result.next_week_style ? STYLE_INFO[result.next_week_style] : null
        const sortedTopics = Object.entries(result.topic_scores ?? {}).sort((a, b) => a[1].pct - b[1].pct)

        return (
            <div className="flex flex-col h-full overflow-hidden">
                <div className={cn(
                    "border-b px-4 sm:px-8 py-5 shrink-0",
                    result.passed ? "bg-emerald-50 dark:bg-emerald-950/20" : "bg-red-50 dark:bg-red-950/20"
                )}>
                    <div className="flex items-center gap-4">
                        {result.passed
                            ? <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
                            : <XCircle className="h-8 w-8 text-red-500 shrink-0" />
                        }
                        <div className="flex-1 min-w-0">
                            <h2 className={cn("text-lg font-bold", result.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>
                                {result.passed ? "Week Passed!" : "Not Quite"}
                            </h2>
                            <p className="text-sm text-muted-foreground">
                                Score: <span className="font-semibold text-foreground">{result.score}%</span>
                                {" · "}{result.passed ? `Week ${week} complete!` : `Need ${result.pass_score}% to pass`}
                            </p>
                        </div>
                        <p className={cn("text-3xl font-black shrink-0", result.passed ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                            {result.score}%
                        </p>
                    </div>

                    {styleInfo && (
                        <div className="mt-4 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 flex items-start gap-3">
                            <Brain className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                            <div>
                                <p className="text-xs font-semibold text-primary">ML Adaptation — Next Week Style: {styleInfo.label}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{styleInfo.description}</p>
                            </div>
                        </div>
                    )}

                    <div className="flex gap-2 mt-4">
                        <Button variant="outline" size="sm" onClick={() => loadQuiz()}>Quiz Overview</Button>
                        <Button size="sm" onClick={startAttempt}>
                            <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Retry
                        </Button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-4">
                        {/* Topic breakdown */}
                        {sortedTopics.length > 1 && (
                            <div className="rounded-xl border bg-card p-4 space-y-3">
                                <h3 className="text-sm font-semibold">Score by Topic</h3>
                                <div className="space-y-2">
                                    {sortedTopics.map(([topic, ts]) => (
                                        <div key={topic} className="space-y-1">
                                            <div className="flex justify-between text-xs">
                                                <span className="text-muted-foreground truncate pr-2">{topic}</span>
                                                <span className={cn("font-semibold shrink-0", ts.pct >= 60 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                                                    {ts.correct}/{ts.total} · {ts.pct}%
                                                </span>
                                            </div>
                                            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                                                <div
                                                    className={cn("h-full rounded-full", ts.pct >= 60 ? "bg-emerald-500" : "bg-red-400")}
                                                    style={{ width: `${ts.pct}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {quiz.questions.map((q, i) => {
                            const r = resultMap[q.id]
                            if (!r) return null
                            return (
                                <div key={q.id} className={cn(
                                    "rounded-xl border p-4 space-y-3",
                                    r.is_correct ? "border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20" : "border-red-200 bg-red-50/50 dark:bg-red-950/20"
                                )}>
                                    <div className="flex items-start gap-2">
                                        {r.is_correct
                                            ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                                            : <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                                        }
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-foreground">
                                                <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                                {q.question}
                                            </p>
                                            {r.topic && r.topic !== "General" && (
                                                <span className="mt-1 inline-block text-xs bg-muted text-muted-foreground rounded px-1.5 py-0.5">{r.topic}</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 gap-1.5 pl-6">
                                        {OPTIONS.map((opt) => {
                                            const text = getOptionText(q, opt)
                                            const isCorrect = opt === r.correct
                                            const isSelected = opt === r.selected
                                            return (
                                                <div key={opt} className={cn(
                                                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm border",
                                                    isCorrect
                                                        ? "border-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 font-medium text-emerald-800 dark:text-emerald-300"
                                                        : isSelected && !isCorrect
                                                            ? "border-red-300 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                                                            : "border-transparent text-muted-foreground"
                                                )}>
                                                    <span className="font-mono text-xs w-4 shrink-0">{opt}.</span>
                                                    <span>{text}</span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                    <p className="pl-6 text-xs text-muted-foreground italic">{r.explanation}</p>
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
