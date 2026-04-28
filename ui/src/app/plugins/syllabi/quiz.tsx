import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router"
import { ArrowLeft, CheckCircle2, XCircle, Loader2, RotateCcw, BookCheck } from "lucide-react"
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
const DIFFICULTY_LABELS: Record<string, string> = {
    beginner: "Beginner",
    intermediate: "Intermediate",
    advanced: "Advanced",
}

function getOptionText(q: QuizQuestion, opt: string): string {
    return ({ A: q.option_a, B: q.option_b, C: q.option_c, D: q.option_d })[opt] ?? ""
}

export default function QuizPage() {
    const { skillId } = useParams<{ skillId: string }>()
    const navigate = useNavigate()

    const [quiz, setQuiz] = useState<QuizData | null>(null)
    const [loading, setLoading] = useState(true)
    const [generating, setGenerating] = useState(false)
    const [error, setError] = useState("")

    const [answers, setAnswers] = useState<Record<number, string>>({})
    const [submitting, setSubmitting] = useState(false)
    const [result, setResult] = useState<SubmitResult | null>(null)

    async function fetchQuiz() {
        setLoading(true)
        setError("")
        const { success, data } = await getRequest(`/py/quiz/${skillId}`)
        if (success) {
            setQuiz(data)
            setAnswers({})
            setResult(null)
        } else {
            // 404 = not generated yet — generate it
            if (data?.status === 404 || !success) {
                await generateQuiz()
                return
            }
            setError("Failed to load quiz.")
        }
        setLoading(false)
    }

    async function generateQuiz() {
        setGenerating(true)
        setError("")
        const { success, data } = await postRequest(`/py/quiz/${skillId}/generate`, {})
        if (success) {
            // Now fetch the actual questions
            const res = await getRequest(`/py/quiz/${skillId}`)
            if (res.success) {
                setQuiz(res.data)
                setAnswers({})
                setResult(null)
            } else {
                setError("Quiz generated but failed to load questions.")
            }
        } else {
            const msg = data?.detail ?? "Failed to generate quiz."
            if (msg.includes("Complete all chapters")) {
                setError("Please complete all chapters before taking the quiz.")
            } else if (msg.includes("already generated")) {
                // Race condition — just fetch
                await fetchQuiz()
                return
            } else {
                setError(msg)
            }
        }
        setGenerating(false)
        setLoading(false)
    }

    useEffect(() => {
        fetchQuiz()
    }, [skillId])

    async function handleSubmit() {
        if (!quiz) return
        const unanswered = quiz.questions.filter((q) => !answers[q.id])
        if (unanswered.length > 0) {
            setError(`Please answer all questions (${unanswered.length} remaining).`)
            return
        }
        setError("")
        setSubmitting(true)
        const { success, data } = await postRequest(`/py/quiz/${skillId}/submit`, { answers })
        if (success) {
            setResult(data)
            // scroll to top
            window.scrollTo({ top: 0, behavior: "smooth" })
        } else {
            setError(data?.detail ?? "Submission failed. Please try again.")
        }
        setSubmitting(false)
    }

    function handleRetry() {
        setResult(null)
        setAnswers({})
        setError("")
        window.scrollTo({ top: 0, behavior: "smooth" })
    }

    if (loading || generating) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground">
                    {generating ? "Generating your quiz… this may take a moment." : "Loading quiz…"}
                </p>
            </div>
        )
    }

    if (error && !quiz) {
        return (
            <div className="max-w-xl mx-auto px-4 py-12 text-center space-y-4">
                <p className="text-destructive text-sm">{error}</p>
                <Button variant="outline" onClick={() => navigate(`/syllabi/${skillId}`)}>
                    <ArrowLeft className="h-4 w-4 mr-1.5" /> Back to Course
                </Button>
            </div>
        )
    }

    if (!quiz) return null

    // ── Result view ──────────────────────────────────────────────────────────
    if (result) {
        const resultMap = Object.fromEntries(result.results.map((r) => [r.question_id, r]))
        return (
            <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
                {/* Score card */}
                <div className={cn(
                    "rounded-2xl border p-6 text-center space-y-2",
                    result.passed
                        ? "border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-800"
                        : "border-red-200 bg-red-50 dark:bg-red-950/30 dark:border-red-800"
                )}>
                    {result.passed
                        ? <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto" />
                        : <XCircle className="h-10 w-10 text-red-500 mx-auto" />
                    }
                    <h2 className={cn("text-2xl font-bold", result.passed ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")}>
                        {result.passed ? "Quiz Passed!" : "Not Quite"}
                    </h2>
                    <p className="text-4xl font-black text-foreground">{result.score}%</p>
                    <p className="text-sm text-muted-foreground">
                        {result.passed
                            ? "You've completed this course!"
                            : `You need ${result.pass_score}% to pass. Keep practicing!`}
                    </p>
                </div>

                {/* Per-question breakdown */}
                <div className="space-y-4">
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
                                                isCorrect ? "border-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 font-medium text-emerald-800 dark:text-emerald-300"
                                                    : isSelected && !isCorrect ? "border-red-300 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
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

                {/* Actions */}
                <div className="flex gap-3 pt-2">
                    <Button variant="outline" onClick={() => navigate(`/syllabi/${skillId}`)}>
                        <ArrowLeft className="h-4 w-4 mr-1.5" /> Back to Course
                    </Button>
                    {!result.passed && (
                        <Button onClick={handleRetry}>
                            <RotateCcw className="h-4 w-4 mr-1.5" /> Retry Quiz
                        </Button>
                    )}
                </div>
            </div>
        )
    }

    // ── Quiz view ────────────────────────────────────────────────────────────
    const answeredCount = Object.keys(answers).length
    const totalCount = quiz.questions.length

    return (
        <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
            {/* Header */}
            <div className="space-y-1">
                <Button variant="ghost" size="sm" className="-ml-2 mb-2" onClick={() => navigate(`/syllabi/${skillId}`)}>
                    <ArrowLeft className="h-4 w-4 mr-1.5" /> Back to Course
                </Button>
                <div className="flex items-center gap-2">
                    <BookCheck className="h-5 w-5 text-primary" />
                    <h1 className="text-xl font-bold tracking-tight">Final Quiz</h1>
                    <span className={cn(
                        "text-xs px-2 py-0.5 rounded-full font-medium border",
                        quiz.difficulty === "advanced" ? "border-red-200 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"
                            : quiz.difficulty === "intermediate" ? "border-amber-200 bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400"
                            : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400"
                    )}>
                        {DIFFICULTY_LABELS[quiz.difficulty] ?? quiz.difficulty}
                    </span>
                </div>
                <p className="text-sm text-muted-foreground">
                    {totalCount} questions · Pass score: {quiz.pass_score}%
                    {quiz.attempt_count > 0 && ` · Attempt ${quiz.attempt_count + 1}`}
                    {quiz.best_score != null && ` · Best: ${quiz.best_score}%`}
                </p>
            </div>

            {/* Progress */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                        className="h-full bg-primary rounded-full transition-all duration-300"
                        style={{ width: `${totalCount > 0 ? (answeredCount / totalCount) * 100 : 0}%` }}
                    />
                </div>
                <span>{answeredCount}/{totalCount} answered</span>
            </div>

            {/* Questions */}
            <div className="space-y-6">
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
            </div>

            {/* Submit */}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="pt-2 pb-8">
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
    )
}
