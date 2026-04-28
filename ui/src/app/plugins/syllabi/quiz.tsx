import { useEffect, useState } from "react"
import { CheckCircle2, XCircle, Loader2, BookCheck, Sparkles, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { getRequest, postRequest } from "@/services"

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
    difficulty: string
    pass_score: number
    status: string
    questions: QuizQuestion[]
    best_score: number | null
    attempt_count: number
}

interface QuestionResult {
    question_id: number
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
}

const OPTIONS = ["A", "B", "C", "D"] as const

const DIFFICULTY_COLORS: Record<string, string> = {
    beginner: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400",
    intermediate: "border-amber-200 bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400",
    advanced: "border-red-200 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400",
}

function getOptionText(q: QuizQuestion, opt: string): string {
    return ({ A: q.option_a, B: q.option_b, C: q.option_c, D: q.option_d } as Record<string, string>)[opt] ?? ""
}

type View = "loading" | "no-quiz" | "generating" | "ready" | "taking" | "submitted"

export function QuizPanel({
    skillId,
    onBack,
    onQuizStatusChange,
}: {
    skillId: string | number
    onBack: () => void
    onQuizStatusChange?: (status: string) => void
}) {
    const [view, setView] = useState<View>("loading")
    const [quiz, setQuiz] = useState<QuizData | null>(null)
    const [generateError, setGenerateError] = useState("")
    const [submitError, setSubmitError] = useState("")
    const [answers, setAnswers] = useState<Record<number, string>>({})
    const [submitting, setSubmitting] = useState(false)
    const [result, setResult] = useState<SubmitResult | null>(null)

    useEffect(() => {
        loadQuiz()
    }, [skillId])

    async function loadQuiz() {
        setView("loading")
        setGenerateError("")
        const { success, data } = await getRequest(`/py/quiz/${skillId}`)
        if (success) {
            setQuiz(data)
            setView("ready")
        } else {
            setQuiz(null)
            setView("no-quiz")
        }
    }

    async function handleGenerate() {
        setView("generating")
        setGenerateError("")
        const { success, data } = await postRequest(`/py/quiz/${skillId}/generate`, {})
        if (success) {
            const res = await getRequest(`/py/quiz/${skillId}`)
            if (res.success) {
                setQuiz(res.data)
                onQuizStatusChange?.("available")
                setView("ready")
            } else {
                setGenerateError("Quiz generated but failed to load. Please refresh.")
                setView("no-quiz")
            }
        } else {
            const msg: string = data?.detail ?? ""
            // 409 or race: quiz already exists — just fetch it
            if (msg.includes("already generated") || data?.status === 409) {
                const res = await getRequest(`/py/quiz/${skillId}`)
                if (res.success) {
                    setQuiz(res.data)
                    setView("ready")
                    return
                }
            }
            setGenerateError(msg || "Failed to generate quiz. Please try again.")
            setView("no-quiz")
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

    function handleRetry() {
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

    // ── Generating ───────────────────────────────────────────────────────────

    if (view === "generating") {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">Generating your quiz… this may take a moment.</p>
            </div>
        )
    }

    // ── No quiz yet ──────────────────────────────────────────────────────────

    if (view === "no-quiz") {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center px-8 gap-5">
                <div className="rounded-full bg-primary/10 p-4">
                    <BookCheck className="h-10 w-10 text-primary" />
                </div>
                <div>
                    <h2 className="text-xl font-bold">Final Quiz</h2>
                    <p className="text-sm text-muted-foreground mt-1.5 max-w-sm">
                        Test your knowledge with a multiple-choice quiz generated from your course topics.
                    </p>
                </div>
                {generateError && <p className="text-sm text-destructive max-w-sm">{generateError}</p>}
                <Button onClick={handleGenerate} size="lg">
                    <Sparkles className="h-4 w-4 mr-2" /> Generate Quiz
                </Button>
            </div>
        )
    }

    // ── Ready (quiz exists, not yet started) ─────────────────────────────────

    if (view === "ready" && quiz) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center px-8 gap-6">
                <div className="rounded-full bg-primary/10 p-4">
                    <BookCheck className="h-10 w-10 text-primary" />
                </div>
                <div className="space-y-1">
                    <h2 className="text-xl font-bold">Final Quiz</h2>
                    <div className="flex items-center justify-center gap-2 mt-2">
                        <span className={cn(
                            "text-xs px-2.5 py-0.5 rounded-full font-medium border capitalize",
                            DIFFICULTY_COLORS[quiz.difficulty] ?? DIFFICULTY_COLORS.beginner
                        )}>
                            {quiz.difficulty}
                        </span>
                    </div>
                    <p className="text-sm text-muted-foreground pt-1">
                        {quiz.questions.length} questions · Pass score: {quiz.pass_score}%
                    </p>
                    {quiz.attempt_count > 0 && (
                        <p className="text-sm text-muted-foreground">
                            {quiz.attempt_count} attempt{quiz.attempt_count !== 1 ? "s" : ""}
                            {quiz.best_score != null && ` · Best score: ${quiz.best_score}%`}
                        </p>
                    )}
                    {quiz.status === "passed" && (
                        <div className="flex items-center justify-center gap-1.5 text-emerald-600 dark:text-emerald-400 pt-1">
                            <CheckCircle2 className="h-4 w-4" />
                            <span className="text-sm font-medium">Quiz passed!</span>
                        </div>
                    )}
                </div>
                <Button onClick={() => setView("taking")} size="lg">
                    <BookCheck className="h-4 w-4 mr-2" />
                    {quiz.attempt_count > 0 ? "Retake Quiz" : "Start Quiz"}
                </Button>
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
                            <span className={cn(
                                "text-xs px-2 py-0.5 rounded-full font-medium border capitalize",
                                DIFFICULTY_COLORS[quiz.difficulty] ?? DIFFICULTY_COLORS.beginner
                            )}>
                                {quiz.difficulty}
                            </span>
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
                        <Button variant="outline" size="sm" onClick={onBack}>
                            Back to Course
                        </Button>
                        <Button size="sm" onClick={handleRetry}>
                            <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Retry Quiz
                        </Button>
                    </div>
                </div>

                {/* Per-question breakdown */}
                <div className="flex-1 overflow-y-auto">
                    <div className="mx-auto w-full max-w-2xl px-4 sm:px-6 py-6 space-y-4">
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
                                        <p className="text-sm font-medium text-foreground">
                                            <span className="text-muted-foreground mr-1.5">Q{i + 1}.</span>
                                            {q.question}
                                        </p>
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
