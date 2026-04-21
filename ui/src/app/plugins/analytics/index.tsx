import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import {
    BookOpen, Clock,
    Flame, Award, ChevronRight, Zap, BarChart2, CalendarDays
} from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { getRequest } from "@/services"
import useStore from "@/store"

interface Syllabus {
    skill_id: number
    skill: string
    days: number
    hours: number
    created_at: string
    total_tasks: number
    completed_tasks: number
}

function getStatus(completed: number, total: number) {
    if (total === 0) return "no-syllabus"
    const pct = (completed / total) * 100
    if (pct === 100) return "completed"
    if (pct > 0) return "in-progress"
    return "not-started"
}

function RingProgress({ pct, size = 80, stroke = 7, color = "#6366f1", trackColor = "rgba(99,102,241,0.12)" }: {
    pct: number; size?: number; stroke?: number; color?: string; trackColor?: string
}) {
    const r = (size - stroke * 2) / 2
    const circ = 2 * Math.PI * r
    const offset = circ - (pct / 100) * circ
    return (
        <svg width={size} height={size} className="-rotate-90">
            <circle cx={size / 2} cy={size / 2} r={r} stroke={trackColor}
                strokeWidth={stroke} fill="none" />
            <circle cx={size / 2} cy={size / 2} r={r} stroke={color}
                strokeWidth={stroke} fill="none" strokeLinecap="round"
                strokeDasharray={circ} strokeDashoffset={offset}
                style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(.4,0,.2,1)" }} />
        </svg>
    )
}

export default function AnalyticsPage() {
    const [syllabi, setSyllabi] = useState<Syllabus[]>([])
    const [loading, setLoading] = useState(true)
    const { setPluginName } = useStore((state: any) => state)
    const fetchedRef = useRef(false)
    const navigate = useNavigate()

    useEffect(() => { setPluginName("Analytics") }, [setPluginName])

    useEffect(() => {
        if (fetchedRef.current) return
        fetchedRef.current = true
        getRequest("/py/syllabi").then(({ success, data }) => {
            if (success) setSyllabi(data)
            setLoading(false)
        })
    }, [])

    const totalCourses = syllabi.length
    const inProgress = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks) === "in-progress")
    const completedCourses = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks) === "completed")
    const notStarted = syllabi.filter(s => getStatus(s.completed_tasks, s.total_tasks) === "not-started")
    const totalDays = syllabi.reduce((sum, s) => sum + s.total_tasks, 0)
    const totalDone = syllabi.reduce((sum, s) => sum + s.completed_tasks, 0)
    const totalHours = syllabi.reduce((sum, s) => sum + s.hours * s.days, 0)
    const overallPct = totalDays > 0 ? Math.round((totalDone / totalDays) * 100) : 0

    const sortedSyllabi = [...syllabi].sort((a, b) => {
        const order: Record<string, number> = { "in-progress": 0, "not-started": 1, "no-syllabus": 2, "completed": 3 }
        return order[getStatus(a.completed_tasks, a.total_tasks)] - order[getStatus(b.completed_tasks, b.total_tasks)]
    })

    if (loading) {
        return (
            <div className="min-h-screen bg-background">
                <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">
                    <div className="space-y-2">
                        <Skeleton className="h-8 w-48" />
                        <Skeleton className="h-4 w-64" />
                    </div>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        <Skeleton className="h-56 rounded-3xl lg:col-span-1" />
                        <div className="lg:col-span-2 grid grid-cols-2 gap-4">
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

    if (totalCourses === 0) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center p-6">
                <div className="text-center max-w-sm">
                    <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-indigo-500/20 to-violet-500/10 mx-auto mb-5">
                        <BarChart2 className="h-9 w-9 text-indigo-500" />
                    </div>
                    <h2 className="text-xl font-bold mb-2">No data yet</h2>
                    <p className="text-muted-foreground text-sm mb-6 leading-relaxed">
                        Enroll in a course to start seeing your learning analytics.
                    </p>
                    <button
                        onClick={() => navigate("/enroll")}
                        className="inline-flex items-center gap-2 rounded-2xl bg-indigo-600 px-6 py-3 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-500/20"
                    >
                        <Zap className="h-4 w-4" /> Start Learning
                    </button>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-background">
            <div className="max-w-5xl mx-auto px-6 py-8 space-y-8">

                {/* ── Header ─────────────────────────────────────────────── */}
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
                    <p className="text-muted-foreground mt-1">Your learning progress at a glance</p>
                </div>

                {/* ── Hero row: big ring + 4 mini stats ──────────────────── */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

                    {/* Big ring card */}
                    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 to-violet-600 p-6 flex flex-col items-center justify-center gap-3 shadow-xl shadow-indigo-500/20 min-h-[200px]">
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
                            <p className="text-indigo-200 text-xs mt-0.5">{totalDone} of {totalDays} days done</p>
                        </div>
                    </div>

                    {/* 4 mini stat cards */}
                    <div className="lg:col-span-2 grid grid-cols-2 gap-4">
                        {/* In Progress */}
                        <div className="rounded-2xl border border-border/60 bg-card p-5 flex items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-500/10">
                                <Flame className="h-5 w-5 text-amber-500" />
                            </div>
                            <div>
                                <p className="text-2xl font-black">{inProgress.length}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">In Progress</p>
                            </div>
                        </div>

                        {/* Completed */}
                        <div className="rounded-2xl border border-border/60 bg-card p-5 flex items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-500/10">
                                <Award className="h-5 w-5 text-emerald-500" />
                            </div>
                            <div>
                                <p className="text-2xl font-black">{completedCourses.length}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Completed</p>
                            </div>
                        </div>

                        {/* Hours planned */}
                        <div className="rounded-2xl border border-border/60 bg-card p-5 flex items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-blue-500/10">
                                <Clock className="h-5 w-5 text-blue-500" />
                            </div>
                            <div>
                                <p className="text-2xl font-black">{totalHours}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Hours Planned</p>
                            </div>
                        </div>

                        {/* Days remaining */}
                        <div className="rounded-2xl border border-border/60 bg-card p-5 flex items-center gap-4">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-violet-500/10">
                                <CalendarDays className="h-5 w-5 text-violet-500" />
                            </div>
                            <div>
                                <p className="text-2xl font-black">{totalDays - totalDone}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">Days Remaining</p>
                            </div>
                        </div>
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
                            <div className="bg-muted-foreground/20 rounded-r-full transition-all duration-700"
                                style={{ width: `${(notStarted.length / totalCourses) * 100}%` }} />
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
                            const status = getStatus(s.completed_tasks, s.total_tasks)
                            const pct = s.total_tasks > 0 ? Math.round((s.completed_tasks / s.total_tasks) * 100) : 0
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
