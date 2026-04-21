import { useEffect, useState, useCallback } from "react"
import { useNavigate } from "react-router"
import {
    BookOpen, Sparkles, PlayCircle, TrendingUp, Clock,
    CalendarDays, ArrowRight, GraduationCap, CheckCircle2, CircleDot, Zap,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { getRequest } from "@/services"
import useStore from "@/store"
import useAuthStore from "@/store/authStore"

interface Syllabus {
    skill_id: number
    skill: string
    days: number
    hours: number
    total_tasks: number
    completed_tasks: number
}

function getGreeting() {
    const h = new Date().getHours()
    if (h < 12) return "Good morning"
    if (h < 17) return "Good afternoon"
    return "Good evening"
}

function getFirstName(name: string) {
    return name?.split(" ")[0] ?? name
}

function ContinueCard({ item, onStart }: { item: Syllabus; onStart: () => void }) {
    const progress = item.total_tasks > 0
        ? Math.round((item.completed_tasks / item.total_tasks) * 100)
        : 0
    const isCompleted = progress === 100

    return (
        <div
            onClick={onStart}
            className="group flex items-center gap-4 rounded-xl border border-border/60 bg-card px-4 py-3.5 hover:border-primary/40 hover:shadow-sm transition-all duration-200 cursor-pointer"
        >
            <div className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                isCompleted ? "bg-emerald-500/10 text-emerald-600" : "bg-indigo-500/10 text-indigo-600"
            )}>
                <BookOpen className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold truncate">{item.skill}</p>
                <div className="flex items-center gap-2 mt-1.5">
                    <Progress value={progress} className="h-1.5 flex-1" />
                    <span className="text-xs text-muted-foreground shrink-0">{progress}%</span>
                </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-muted-foreground hidden sm:block">
                    {item.completed_tasks}/{item.total_tasks} days
                </span>
                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all" />
            </div>
        </div>
    )
}

function StatCard({ icon: Icon, label, value, color }: {
    icon: React.ElementType
    label: string
    value: number | string
    color: string
}) {
    return (
        <div className="flex flex-col gap-2 rounded-xl border border-border/60 bg-card p-4">
            <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", color)}>
                <Icon className="h-4 w-4" />
            </div>
            <div>
                <p className="text-2xl font-bold leading-none">{value}</p>
                <p className="text-xs text-muted-foreground mt-1">{label}</p>
            </div>
        </div>
    )
}

export default function HomePage() {
    const navigate = useNavigate()
    const { setPluginName } = useStore((state: any) => state)
    const { user } = useAuthStore()
    const [syllabi, setSyllabi] = useState<Syllabus[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        setPluginName("")
    }, [setPluginName])

    const fetchSyllabi = useCallback(async () => {
        const { success, data } = await getRequest("/py/syllabi")
        if (success) setSyllabi(data)
        setLoading(false)
    }, [])

    useEffect(() => {
        fetchSyllabi()
    }, [fetchSyllabi])

    const total = syllabi.length
    const inProgress = syllabi.filter(s => s.total_tasks > 0 && s.completed_tasks > 0 && s.completed_tasks < s.total_tasks)
    const completed = syllabi.filter(s => s.total_tasks > 0 && s.completed_tasks === s.total_tasks)
    const totalHours = syllabi.reduce((acc, s) => acc + s.hours * s.days, 0)

    const continueSyllabi = [
        ...inProgress,
        ...syllabi.filter(s => s.total_tasks > 0 && s.completed_tasks === 0),
    ].slice(0, 4)

    return (
        <div className="p-6 md:p-8 max-w-4xl space-y-8">

            {/* Hero greeting */}
            <div className="rounded-2xl border border-border/60 bg-gradient-to-br from-primary/5 via-background to-indigo-500/5 p-6 md:p-8">
                <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1.5">
                        <p className="text-sm text-muted-foreground font-medium">{getGreeting()}</p>
                        <h1 className="text-2xl md:text-3xl font-bold tracking-tight">
                            {user?.name ? getFirstName(user.name) : "Welcome"} 👋
                        </h1>
                        <p className="text-muted-foreground text-sm md:text-base max-w-md">
                            {total === 0
                                ? "Your AI-powered learning journey starts here. Enroll in a course and we'll build a personalised syllabus for you."
                                : inProgress.length > 0
                                ? `You have ${inProgress.length} course${inProgress.length > 1 ? "s" : ""} in progress. Keep the momentum going!`
                                : "Great work — keep learning and building new skills every day."
                            }
                        </p>
                    </div>
                    <div className="hidden md:flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                        <Zap className="h-7 w-7" />
                    </div>
                </div>
                <div className="mt-5 flex flex-wrap gap-2">
                    {total === 0 ? (
                        <Button onClick={() => navigate("/enroll")} className="gap-2">
                            <Sparkles className="h-4 w-4" />
                            Start your first course
                        </Button>
                    ) : (
                        <>
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
                        </>
                    )}
                </div>
            </div>

            {/* Stats */}
            {loading ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {Array.from({ length: 4 }).map((_, i) => (
                        <div key={i} className="rounded-xl border border-border/60 bg-card p-4 space-y-2">
                            <Skeleton className="h-8 w-8 rounded-lg" />
                            <Skeleton className="h-6 w-10" />
                            <Skeleton className="h-3 w-20" />
                        </div>
                    ))}
                </div>
            ) : total > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <StatCard icon={GraduationCap} label="Total courses" value={total} color="bg-primary/10 text-primary" />
                    <StatCard icon={CircleDot} label="In progress" value={inProgress.length} color="bg-indigo-500/10 text-indigo-600" />
                    <StatCard icon={CheckCircle2} label="Completed" value={completed.length} color="bg-emerald-500/10 text-emerald-600" />
                    <StatCard icon={Clock} label="Hours planned" value={totalHours} color="bg-amber-500/10 text-amber-600" />
                </div>
            ) : null}


            {/* Empty state */}
            {!loading && total === 0 && (
                <div className="rounded-2xl border border-dashed border-border bg-muted/20 p-10 text-center space-y-4">
                    <div className="flex items-center justify-center gap-3 text-muted-foreground">
                        <BookOpen className="h-5 w-5" />
                        <span className="text-sm font-medium">No courses yet</span>
                        <BookOpen className="h-5 w-5" />
                    </div>
                    <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                        Pick a subject — Python, Machine Learning, System Design, or anything you want — and AI will generate your full syllabus.
                    </p>
                    <div className="flex flex-wrap gap-2 justify-center pt-1">
                        {["Python", "React", "Machine Learning", "System Design"].map(s => (
                            <span key={s} className="text-xs px-3 py-1.5 rounded-full border border-border bg-background text-muted-foreground">
                                {s}
                            </span>
                        ))}
                        <span className="text-xs px-3 py-1.5 rounded-full border border-dashed border-border text-muted-foreground">
                            + more
                        </span>
                    </div>
                    <Button onClick={() => navigate("/enroll")} className="gap-2 mt-2">
                        <Sparkles className="h-4 w-4" />
                        Enroll in your first course
                    </Button>
                </div>
            )}

            {/* Feature highlights — shown only when no courses */}
            {!loading && total === 0 && (
                <div className="grid sm:grid-cols-3 gap-3">
                    {[
                        {
                            icon: Sparkles,
                            title: "AI-Generated Syllabus",
                            desc: "Get a day-by-day learning plan tailored to your pace and schedule.",
                            color: "bg-violet-500/10 text-violet-600",
                        },
                        {
                            icon: BookOpen,
                            title: "Rich Chapter Content",
                            desc: "Every chapter is generated with code examples, explanations, and exercises.",
                            color: "bg-indigo-500/10 text-indigo-600",
                        },
                        {
                            icon: CalendarDays,
                            title: "Learn at Your Pace",
                            desc: "Choose 30 to 180 days and 1–4 hours per day to match your schedule.",
                            color: "bg-sky-500/10 text-sky-600",
                        },
                    ].map(({ icon: Icon, title, desc, color }) => (
                        <div key={title} className="rounded-xl border border-border/60 bg-card p-4 space-y-2">
                            <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", color)}>
                                <Icon className="h-4 w-4" />
                            </div>
                            <p className="text-sm font-semibold">{title}</p>
                            <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
