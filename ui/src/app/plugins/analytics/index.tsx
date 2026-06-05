import { useEffect, useState } from "react"
import { useNavigate, useLocation } from "react-router"
import {
    BookOpen, Clock,
    Flame, Award, ChevronRight, Zap, BarChart2, CalendarDays, Sparkles, PlayCircle, TrendingUp,
    Cpu, DollarSign,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { getRequest } from "@/services"
import useStore from "@/store"
import useAuthStore from "@/store/authStore"

function getGreeting() {
    const h = new Date().getHours()
    if (h < 12) return "Good morning"
    if (h < 17) return "Good afternoon"
    return "Good evening"
}

function getFirstName(name: string) {
    return name?.split(" ")[0] ?? name
}

interface Syllabus {
    skill_id: number
    skill: string
    days: number
    hours: number
    created_at: string
    total_tasks: number
    completed_tasks: number
    quiz_status: string   // "not_generated" | "available" | "passed"
}

function getStatus(completed: number, total: number, quizStatus: string) {
    if (total === 0) return "no-syllabus"
    const completionPercentage = (completed / total) * 100
    // A course is only "completed" when all chapters done AND quiz passed
    if (completionPercentage === 100 && quizStatus === "passed") return "completed"
    if (completionPercentage > 0 || quizStatus === "passed") return "in-progress"
    return "not-started"
}

function RingProgress({ pct, size = 80, stroke = 7, color = "#6366f1", trackColor = "rgba(99,102,241,0.12)" }: {
    pct: number; size?: number; stroke?: number; color?: string; trackColor?: string
}) {
    const radius = (size - stroke * 2) / 2
    const circumference = 2 * Math.PI * radius
    const offset = circumference - (pct / 100) * circumference
    return (
        <svg width={size} height={size} className="-rotate-90">
            <circle cx={size / 2} cy={size / 2} r={radius} stroke={trackColor}
                strokeWidth={stroke} fill="none" />
            <circle cx={size / 2} cy={size / 2} r={radius} stroke={color}
                strokeWidth={stroke} fill="none" strokeLinecap="round"
                strokeDasharray={circumference} strokeDashoffset={offset}
                style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(.4,0,.2,1)" }} />
        </svg>
    )
}

export default function AnalyticsPage() {
    const [syllabi, setSyllabi] = useState<Syllabus[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<Error | null>(null)
    const [streak, setStreak] = useState({ current_streak: 0, longest_streak: 0 })
    const [costData, setCostData] = useState<{
        total_input_tokens: number
        total_output_tokens: number
        total_cost_usd: number
        total_cost_display: number
        display_currency: string
    } | null>(null)
    const [refreshTick, setRefreshTick] = useState(0)
    const { setPluginName } = useStore((state: any) => state)
    const { user } = useAuthStore()
    const navigate = useNavigate()
    const location = useLocation()

    useEffect(() => { setPluginName("Analytics") }, [setPluginName])

    useEffect(() => {
        setLoading(true)
        setCostData(null)
        getRequest("/py/syllabi")
            .then(({ success, data }) => {
                if (success) setSyllabi(data)
                else setError(new Error("Failed to fetch syllabi"))
            })
            .catch(err => setError(err))
            .finally(() => setLoading(false))
        getRequest("/py/streak").then(({ success, data }) => {
            if (success) setStreak(data)
        })
        getRequest(`/py/analytics/cost?t=${Date.now()}`).then(({ success, data }) => {
            if (success) setCostData(data)
        })
    }, [location.key, refreshTick])

    const totalCourses = syllabi.length
    const inProgress = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks, s.quiz_status ?? "not_generated") === "in-progress")
    const completedCourses = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks, s.quiz_status ?? "not_generated") === "completed")
    const notStarted = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks, s.quiz_status ?? "not_generated") === "not-started")
    const noSyllabus = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks, s.quiz_status ?? "not_generated") === "no-syllabus")
    const totalTasks = syllabi.reduce((sum, s) => sum + s.total_tasks, 0)
    const totalTaskDone = syllabi.reduce((sum, s) => sum + s.completed_tasks, 0)
    const totalHours = syllabi.reduce((sum, s) => sum + s.hours * s.days, 0)
    const remainingTasks = Math.max(0, totalTasks - totalTaskDone)
    // Quiz counts as +1 step per course that has a syllabus
    const coursesWithSyllabus = syllabi.filter(s => s.total_tasks > 0)
    const totalStepsOverall = totalTasks + coursesWithSyllabus.length
    const completedStepsOverall = totalTaskDone + coursesWithSyllabus.filter(s => s.quiz_status === "passed").length
    const overallPct = totalStepsOverall > 0 ? Math.round((completedStepsOverall / totalStepsOverall) * 100) : 0

    const sortedSyllabi = [...syllabi].sort((a, b) => {
        const order: Record<string, number> = { "in-progress": 0, "not-started": 1, "no-syllabus": 2, "completed": 3 }
        return order[getStatus(a.completed_tasks, a.total_tasks, a.quiz_status ?? "not_generated")] - order[getStatus(b.completed_tasks, b.total_tasks, b.quiz_status ?? "not_generated")]
    })

    if (loading) {
        return (
            <div className="min-h-screen bg-background">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 sm:py-8 space-y-5 sm:space-y-8">
                    <div className="space-y-2">
                        <Skeleton className="h-8 w-48" />
                        <Skeleton className="h-4 w-64" />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">
                        <Skeleton className="h-48 rounded-3xl" />
                        <div className="sm:col-span-2 grid grid-cols-2 gap-3 sm:gap-4">
                            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}
                        </div>
                    </div>
                    <Skeleton className="h-12 rounded-2xl" />
                    <div className="space-y-3">
                        {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-2xl" />)}
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center p-6">
                <div className="text-center max-w-sm">
                    <p className="text-sm font-medium text-destructive">Failed to load analytics</p>
                    <p className="text-xs text-muted-foreground mt-1">{error.message}</p>
                </div>
            </div>
        )
    }

    if (totalCourses === 0) {
        return (
            <div className="min-h-screen bg-background">
                <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10 sm:py-16 space-y-8">

                    {/* Hero */}
                    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-600 p-8 sm:p-12 text-center shadow-xl shadow-indigo-500/20">
                        <div className="absolute inset-0 opacity-10"
                            style={{ backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)", backgroundSize: "24px 24px" }} />
                        <div className="relative z-10 space-y-4">
                            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 mx-auto">
                                <Zap className="h-8 w-8 text-white" />
                            </div>
                            <div>
                                <h1 className="text-2xl sm:text-3xl font-black text-white">
                                    {user?.name ? `Welcome, ${getFirstName(user.name)}!` : "Welcome!"}
                                </h1>
                                <p className="text-indigo-200 mt-2 text-sm sm:text-base max-w-md mx-auto leading-relaxed">
                                    Enroll in your first course and Openship will build a personalised AI learning plan just for you.
                                </p>
                            </div>
                            <button
                                onClick={() => navigate("/enroll")}
                                className="inline-flex items-center gap-2 rounded-2xl bg-white px-7 py-3 text-sm font-bold text-indigo-600 hover:bg-indigo-50 transition-colors shadow-lg mt-2"
                            >
                                <Sparkles className="h-4 w-4" /> Enroll in a Course
                            </button>
                        </div>
                    </div>

                    {/* What you'll get */}
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground text-center mb-4">What you'll get</p>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <div className="rounded-2xl border border-border/60 bg-card p-5 space-y-2">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10">
                                    <BarChart2 className="h-5 w-5 text-indigo-500" />
                                </div>
                                <p className="font-semibold text-sm">Progress Tracking</p>
                                <p className="text-xs text-muted-foreground leading-relaxed">See your completion rate, streaks, and overall progress at a glance.</p>
                            </div>
                            <div className="rounded-2xl border border-border/60 bg-card p-5 space-y-2">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10">
                                    <Sparkles className="h-5 w-5 text-violet-500" />
                                </div>
                                <p className="font-semibold text-sm">AI-Personalised Plan</p>
                                <p className="text-xs text-muted-foreground leading-relaxed">Weekly plans adapt to your weak spots and learning style automatically.</p>
                            </div>
                            <div className="rounded-2xl border border-border/60 bg-card p-5 space-y-2">
                                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
                                    <Flame className="h-5 w-5 text-amber-500" />
                                </div>
                                <p className="font-semibold text-sm">Daily Streaks</p>
                                <p className="text-xs text-muted-foreground leading-relaxed">Build a learning habit and track your consistency with streak tracking.</p>
                            </div>
                        </div>
                    </div>

                    {/* Preview of dashboard stats */}
                    <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 space-y-3">
                        <p className="text-xs text-muted-foreground text-center font-medium">Your dashboard will look like this once you enroll</p>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 opacity-40 pointer-events-none select-none">
                            {[
                                { icon: TrendingUp, label: "In Progress", val: "3", color: "bg-amber-500/10", iconColor: "text-amber-500" },
                                { icon: Award, label: "Completed", val: "1", color: "bg-emerald-500/10", iconColor: "text-emerald-500" },
                                { icon: Flame, label: "Day Streak", val: "12", color: "bg-orange-500/10", iconColor: "text-orange-500" },
                                { icon: Clock, label: "Hours Planned", val: "90", color: "bg-blue-500/10", iconColor: "text-blue-500" },
                            ].map(({ icon: Icon, label, val, color, iconColor }) => (
                                <div key={label} className="rounded-xl border border-border/60 bg-card p-4 flex items-center gap-3">
                                    <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${color}`}>
                                        <Icon className={`h-4 w-4 ${iconColor}`} />
                                    </div>
                                    <div>
                                        <p className="text-lg font-black">{val}</p>
                                        <p className="text-[10px] text-muted-foreground">{label}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-background">
            <div className="max-w-5xl mx-auto px-4 sm:px-6 py-5 sm:py-8 space-y-5 sm:space-y-8">

                {/* ── Greeting hero ──────────────────────────────────────── */}
                <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-background to-indigo-500/5 p-4 sm:p-6 md:p-8">
                    <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1.5">
                            <p className="text-sm text-muted-foreground font-medium">{getGreeting()}</p>
                            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold tracking-tight">
                                {user?.name ? getFirstName(user.name) : "Welcome"} 👋
                            </h1>
                            <p className="text-muted-foreground text-sm md:text-base max-w-md">
                                {inProgress.length > 0
                                    ? `You have ${inProgress.length} course${inProgress.length > 1 ? "s" : ""} in progress. Keep the momentum going!`
                                    : "Great work — keep learning and building new skills every day."
                                }
                            </p>
                        </div>
                        <div className="hidden md:flex shrink-0 items-center justify-center relative">
                            <span className="text-6xl leading-none select-none">🔥</span>
                            {streak.current_streak > 0 && (
                                <span className="absolute text-lg font-black text-white mt-4"
                                    style={{ textShadow: "0 1px 3px rgba(0,0,0,0.5)" }}>
                                    {streak.current_streak}
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="mt-5 flex flex-wrap gap-2">
                        {inProgress.length > 0 && (
                            <Button onClick={() => navigate("/syllabi")} className="gap-2">
                                <PlayCircle className="h-4 w-4" />
                                Continue Learning
                            </Button>
                        )}
                        <Button variant="outline" onClick={() => navigate("/enroll")} className="gap-2">
                            <Sparkles className="h-4 w-4" />
                            New Course
                        </Button>
                    </div>
                </div>

                {/* ── Hero row: big ring + 4 mini stats ──────────────────── */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-5">

                    {/* Big ring card */}
                    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-600 p-6 flex flex-col items-center justify-center gap-3 shadow-xl shadow-indigo-500/20 min-h-[180px] sm:min-h-[200px]">
                        {/* subtle grid pattern */}
                        <div className="absolute inset-0 opacity-10"
                            style={{ backgroundImage: "radial-gradient(circle, white 1px, transparent 1px)", backgroundSize: "20px 20px" }} />
                        <div className="relative flex items-center justify-center">
                            <RingProgress pct={overallPct} size={120} stroke={10} color="white" trackColor="rgba(255,255,255,0.2)" />
                            <div className="absolute text-center">
                                <span className="text-3xl font-black text-white">{overallPct}%</span>
                            </div>
                        </div>
                        <div className="text-center relative z-10">
                            <p className="text-white font-semibold text-sm">Overall Completion</p>
                            <p className="text-indigo-200 text-xs mt-0.5">{completedStepsOverall} of {totalStepsOverall} steps done</p>
                        </div>
                    </div>

                    {/* 4 mini stat cards */}
                    <div className="sm:col-span-2 grid grid-cols-2 gap-3 sm:gap-4">
                        {/* In Progress */}
                        <div className="rounded-2xl border border-border/60 bg-card p-3 sm:p-5 flex items-center gap-3 sm:gap-4">
                            <div className="flex h-9 w-9 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-500/10">
                                <TrendingUp className="h-4 w-4 sm:h-5 sm:w-5 text-amber-500" />
                            </div>
                            <div>
                                <p className="text-xl sm:text-2xl font-black">{inProgress.length}</p>
                                <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">In Progress</p>
                            </div>
                        </div>

                        {/* Completed */}
                        <div className="rounded-2xl border border-border/60 bg-card p-3 sm:p-5 flex items-center gap-3 sm:gap-4">
                            <div className="flex h-9 w-9 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-500/10">
                                <Award className="h-4 w-4 sm:h-5 sm:w-5 text-emerald-500" />
                            </div>
                            <div>
                                <p className="text-xl sm:text-2xl font-black">{completedCourses.length}</p>
                                <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">Completed</p>
                            </div>
                        </div>

                        {/* Hours planned */}
                        <div className="rounded-2xl border border-border/60 bg-card p-3 sm:p-5 flex items-center gap-3 sm:gap-4">
                            <div className="flex h-9 w-9 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-2xl bg-blue-500/10">
                                <Clock className="h-4 w-4 sm:h-5 sm:w-5 text-blue-500" />
                            </div>
                            <div>
                                <p className="text-xl sm:text-2xl font-black">{totalHours}</p>
                                <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">Hours Planned</p>
                            </div>
                        </div>

                        {/* Days remaining */}
                        <div className="rounded-2xl border border-border/60 bg-card p-3 sm:p-5 flex items-center gap-3 sm:gap-4">
                            <div className="flex h-9 w-9 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-2xl bg-violet-500/10">
                                <CalendarDays className="h-4 w-4 sm:h-5 sm:w-5 text-violet-500" />
                            </div>
                            <div>
                                <p className="text-xl sm:text-2xl font-black">{remainingTasks}</p>
                                <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">Tasks Remaining</p>
                            </div>
                        </div>

                        {/* Current streak */}
                        <div className="rounded-2xl border border-border/60 bg-card p-5 flex items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-500/10">
                                <Flame className="h-5 w-5 text-amber-500" />
                            </div>
                            <div>
                                <p className="text-2xl font-black">{streak.current_streak}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Current Streak</p>
                            </div>
                        </div>

                        {/* Longest streak */}
                        <div className="rounded-2xl border border-border/60 bg-card p-5 flex items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-violet-500/10">
                                <Zap className="h-5 w-5 text-violet-500" />
                            </div>
                            <div>
                                <p className="text-2xl font-black">{streak.longest_streak}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Longest Streak</p>
                            </div>
                        </div>

                        {/* Tokens used */}
                        {costData && (costData.total_input_tokens + costData.total_output_tokens) > 0 && (
                            <div className="rounded-2xl border border-border/60 bg-card p-3 sm:p-5 flex items-center gap-3 sm:gap-4">
                                <div className="flex h-9 w-9 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-2xl bg-cyan-500/10">
                                    <Cpu className="h-4 w-4 sm:h-5 sm:w-5 text-cyan-500" />
                                </div>
                                <div className="flex-1">
                                    <p className="text-xl sm:text-2xl font-black">
                                        {((costData.total_input_tokens + costData.total_output_tokens) / 1000).toFixed(1)}K
                                    </p>
                                    <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">Tokens Used</p>
                                </div>
                                <button
                                    onClick={() => setRefreshTick(t => t + 1)}
                                    title="Refresh stats"
                                    className="text-muted-foreground/40 hover:text-muted-foreground transition-colors"
                                >
                                    <TrendingUp className="h-3.5 w-3.5 rotate-90" />
                                </button>
                            </div>
                        )}

                        {/* Total spent */}
                        {costData && costData.total_cost_usd > 0 && (
                            <div className="rounded-2xl border border-border/60 bg-card p-3 sm:p-5 flex items-center gap-3 sm:gap-4">
                                <div className="flex h-9 w-9 sm:h-11 sm:w-11 shrink-0 items-center justify-center rounded-2xl bg-rose-500/10">
                                    <DollarSign className="h-4 w-4 sm:h-5 sm:w-5 text-rose-500" />
                                </div>
                                <div>
                                    <p className="text-xl sm:text-2xl font-black">
                                        {costData.total_cost_display.toFixed(4)}
                                        {costData.display_currency !== "USD" && (
                                            <span className="text-sm font-semibold ml-1 text-muted-foreground">{costData.display_currency}</span>
                                        )}
                                    </p>
                                    <p className="text-[10px] sm:text-xs text-muted-foreground mt-0.5">Total Spent</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* ── Status distribution bar ─────────────────────────────── */}
                <div className="rounded-2xl border border-border/60 bg-card p-5 space-y-3">
                    <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold">Course Distribution</p>
                        <p className="text-xs text-muted-foreground">{totalCourses} courses total</p>
                    </div>
                    <div className="flex h-2.5 w-full overflow-hidden rounded-full gap-1">
                        {completedCourses.length > 0 && (
                            <div className="bg-emerald-500 rounded-l-full transition-all duration-700"
                                style={{ width: `${(completedCourses.length / totalCourses) * 100}%` }} />
                        )}
                        {inProgress.length > 0 && (
                            <div className="bg-indigo-500 transition-all duration-700"
                                style={{ width: `${(inProgress.length / totalCourses) * 100}%` }} />
                        )}
                        {notStarted.length > 0 && (
                            <div className="bg-muted-foreground/20 transition-all duration-700"
                                style={{ width: `${(notStarted.length / totalCourses) * 100}%` }} />
                        )}
                        {noSyllabus.length > 0 && (
                            <div className="bg-muted-foreground/10 rounded-r-full transition-all duration-700"
                                style={{ width: `${(noSyllabus.length / totalCourses) * 100}%` }} />
                        )}
                    </div>
                    <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
                        {completedCourses.length > 0 && (
                            <span className="flex items-center gap-1.5">
                                <span className="h-2 w-2 rounded-full bg-emerald-500 inline-block" />
                                Completed <span className="font-semibold text-foreground ml-0.5">{completedCourses.length}</span>
                            </span>
                        )}
                        {inProgress.length > 0 && (
                            <span className="flex items-center gap-1.5">
                                <span className="h-2 w-2 rounded-full bg-indigo-500 inline-block" />
                                In Progress <span className="font-semibold text-foreground ml-0.5">{inProgress.length}</span>
                            </span>
                        )}
                        {notStarted.length > 0 && (
                            <span className="flex items-center gap-1.5">
                                <span className="h-2 w-2 rounded-full bg-muted-foreground/40 inline-block" />
                                Not Started <span className="font-semibold text-foreground ml-0.5">{notStarted.length}</span>
                            </span>
                        )}
                        {noSyllabus.length > 0 && (
                            <span className="flex items-center gap-1.5">
                                <span className="h-2 w-2 rounded-full bg-muted-foreground/20 inline-block" />
                                No Syllabus <span className="font-semibold text-foreground ml-0.5">{noSyllabus.length}</span>
                            </span>
                        )}
                    </div>
                </div>

                {/* ── Course breakdown ────────────────────────────────────── */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-base font-semibold">Course Breakdown</h2>
                        <button
                            onClick={() => navigate("/syllabi")}
                            className="flex items-center gap-0.5 text-xs text-indigo-500 hover:text-indigo-600 font-medium transition-colors"
                        >
                            View all <ChevronRight className="h-3.5 w-3.5" />
                        </button>
                    </div>

                    <div className="space-y-2.5">
                        {sortedSyllabi.map((s) => {
                            const status = getStatus(s.completed_tasks, s.total_tasks, s.quiz_status ?? "not_generated")
                            const totalSteps = s.total_tasks > 0 ? s.total_tasks + 1 : 0
                            const completedSteps = s.completed_tasks + (s.quiz_status === "passed" ? 1 : 0)
                            const pct = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0
                            const ringColor = status === "completed" ? "#10b981" : status === "in-progress" ? "#6366f1" : "#94a3b8"
                            const trackColor = status === "completed" ? "rgba(16,185,129,0.15)" : status === "in-progress" ? "rgba(99,102,241,0.15)" : "rgba(148,163,184,0.15)"

                            return (
                                <button
                                    key={s.skill_id}
                                    onClick={() => navigate(`/syllabi/${s.skill_id}`)}
                                    className="w-full text-left flex items-center gap-4 rounded-2xl border border-border/60 bg-card hover:border-indigo-300/60 hover:bg-indigo-50/30 dark:hover:bg-indigo-950/20 px-5 py-4 transition-all duration-200 group"
                                >
                                    {/* Mini ring */}
                                    <div className="relative flex-shrink-0 flex items-center justify-center">
                                        <RingProgress pct={pct} size={48} stroke={4} color={ringColor} trackColor={trackColor} />
                                        <span className="absolute text-[10px] font-black" style={{ color: ringColor }}>{pct}%</span>
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0 space-y-2">
                                        <div className="flex items-center gap-2">
                                            <p className="text-sm font-semibold truncate">{s.skill}</p>
                                            <span className={`shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                                                status === "completed"
                                                    ? "bg-emerald-500/10 text-emerald-600"
                                                    : status === "in-progress"
                                                    ? "bg-indigo-500/10 text-indigo-600"
                                                    : "bg-muted text-muted-foreground"
                                            }`}>
                                                {status === "completed" ? "Completed"
                                                    : status === "in-progress" ? "In Progress"
                                                    : status === "not-started" ? "Not Started"
                                                    : "No Syllabus"}
                                            </span>
                                        </div>
                                        {s.total_tasks > 0 ? (
                                            <div className="flex items-center gap-3">
                                                <Progress value={pct} className="h-1.5 flex-1" />
                                                <span className="text-xs text-muted-foreground shrink-0 tabular-nums">
                                                    {s.completed_tasks}/{s.total_tasks}
                                                </span>
                                            </div>
                                        ) : (
                                            <p className="text-xs text-muted-foreground">No syllabus generated yet</p>
                                        )}
                                    </div>

                                    {/* Sub-stats */}
                                    <div className="hidden sm:flex flex-col items-end gap-1 shrink-0 text-xs text-muted-foreground">
                                        <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{s.hours}h/day</span>
                                        <span className="flex items-center gap-1"><BookOpen className="h-3 w-3" />{s.days} days</span>
                                    </div>

                                    <ChevronRight className="h-4 w-4 text-muted-foreground/30 group-hover:text-indigo-400 shrink-0 transition-colors" />
                                </button>
                            )
                        })}
                    </div>
                </div>


            </div>
        </div>
    )
}
