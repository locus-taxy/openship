import { useEffect, useRef, useState, useCallback } from "react"
import { useNavigate } from "react-router"
import { BookOpen, Clock, CalendarDays, TrendingUp, Sparkles, PlayCircle, Loader2, RotateCw, Search, FileText, GraduationCap, CheckCircle2, CircleDot } from "lucide-react"
import {
    Dialog, DialogContent, DialogDescription, DialogFooter,
    DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { LlmBar } from "@/components/llm-bar"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { getRequest } from "@/services"
import api from "@/services"
import { useToast } from "@/hooks/use-toast"
import { ToastAction } from "@/components/ui/toast"
import useStore from "@/store"

interface MatchingChapter {
    id: number
    day: number
    topic: string
    task: string
}

interface Syllabus {
    skill_id: number
    skill: string
    days: number
    hours: number
    created_at: string
    total_tasks: number
    completed_tasks: number
    matching_chapters?: MatchingChapter[]
}

function SyllabusCard({ item, onSyllabusGenerated, onStart, searchQuery }: {
    item: Syllabus
    onSyllabusGenerated: (skillId: number) => void
    onStart: (skillId: number) => void
    searchQuery: string
}) {
    const [generating, setGenerating] = useState(false)
    const [confirmOpen, setConfirmOpen] = useState(false)
    const { toast } = useToast()
    const { setSettingsOpen } = useStore((s: any) => s)
    const chapters = item.matching_chapters ?? []
    const hasMatchingChapters = searchQuery.trim() !== "" && chapters.length > 0

    const progress = item.total_tasks > 0
        ? Math.round((item.completed_tasks / item.total_tasks) * 100)
        : 0
    const hasSyllabus = item.total_tasks > 0
    const isCompleted = progress === 100
    const isInProgress = progress > 0 && progress < 100

    async function handleGenerate(e?: React.MouseEvent) {
        e?.stopPropagation()
        setConfirmOpen(false)
        setGenerating(true)
        try {
            await api.post("/py/generate-syllabus", { skill: item.skill })
            onSyllabusGenerated(item.skill_id)
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
                toast({ variant: "destructive", title: "Error", description: detail || "Failed to generate syllabus." })
            }
        } finally {
            setGenerating(false)
        }
    }

    return (
        <Card className="relative overflow-hidden border border-border/60 bg-card hover:shadow-md hover:border-border transition-all duration-200 flex flex-col group">
            {/* Top accent bar */}
            <div className={cn(
                "absolute top-0 left-0 right-0 h-0.5",
                isCompleted
                    ? "bg-gradient-to-r from-emerald-400 to-teal-500"
                    : isInProgress
                    ? "bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500"
                    : hasSyllabus
                    ? "bg-gradient-to-r from-zinc-300 to-zinc-400"
                    : "bg-gradient-to-r from-violet-500 via-indigo-500 to-blue-500"
            )} />

            <CardHeader className="pb-2 pt-4 px-3 sm:px-6 sm:pb-3 sm:pt-5">
                <div className="flex items-start justify-between gap-1.5 sm:gap-2">
                    <div className="flex items-start gap-2 sm:gap-3 min-w-0">
                        <div className={cn(
                            "flex h-7 w-7 sm:h-9 sm:w-9 shrink-0 items-center justify-center rounded-lg",
                            isCompleted
                                ? "bg-emerald-500/10 text-emerald-600"
                                : isInProgress
                                ? "bg-indigo-500/10 text-indigo-600"
                                : "bg-primary/10 text-primary"
                        )}>
                            <BookOpen className="h-3.5 w-3.5 sm:h-4.5 sm:w-4.5" />
                        </div>
                        <h3 className="text-sm sm:text-base font-semibold leading-snug line-clamp-2 pt-0.5">{item.skill}</h3>
                    </div>
                    {hasSyllabus && (
                        <Badge
                            variant="outline"
                            className={cn(
                                "shrink-0 text-[10px] sm:text-xs font-medium px-1.5 sm:px-2",
                                isCompleted
                                    ? "bg-emerald-500/10 text-emerald-600 border-emerald-200"
                                    : isInProgress
                                    ? "bg-indigo-500/10 text-indigo-600 border-indigo-200"
                                    : "text-muted-foreground"
                            )}
                        >
                            <span className="hidden sm:inline">{isCompleted ? "Completed" : isInProgress ? "In Progress" : "Not Started"}</span>
                            <span className="sm:hidden">{isCompleted ? "✓" : isInProgress ? "…" : "—"}</span>
                        </Badge>
                    )}
                </div>
            </CardHeader>

            <CardContent className="flex-1 flex flex-col pt-0 px-3 sm:px-6">
                {hasSyllabus || hasMatchingChapters ? (
                    <div className="space-y-4 flex-1 flex flex-col">
                        {hasSyllabus && (
                            <div className="space-y-1.5">
                                <div className="flex justify-between text-xs text-muted-foreground">
                                    <span className="flex items-center gap-1">
                                        <TrendingUp className="h-3 w-3" />Progress
                                    </span>
                                    <span className="font-medium text-foreground">{item.completed_tasks} / {item.total_tasks} days</span>
                                </div>
                                <Progress value={progress} className="h-1.5" />
                                <p className="text-right text-xs font-semibold text-primary">{progress}%</p>
                            </div>
                        )}

                        {hasMatchingChapters && (
                            <div className="space-y-1.5">
                                <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                                    <FileText className="h-3 w-3" />
                                    Matching chapters ({chapters.length})
                                </p>
                                <ul className="space-y-1 h-[6.5rem] overflow-y-auto">
                                    {chapters.map((ch) => (
                                        <li key={ch.id} className="text-xs rounded-md bg-muted/50 px-2.5 py-1.5">
                                            <span className="font-medium">Day {ch.day}:</span>{" "}
                                            <span className="text-muted-foreground">{ch.topic}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        <div className="grid grid-cols-2 gap-1.5 sm:gap-2">
                            <div className="flex items-center gap-1.5 sm:gap-2 rounded-lg bg-muted/50 px-2 sm:px-3 py-1.5 sm:py-2">
                                <CalendarDays className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-muted-foreground shrink-0" />
                                <div>
                                    <p className="text-[10px] sm:text-xs text-muted-foreground">Duration</p>
                                    <p className="text-xs sm:text-sm font-semibold">{item.days}d</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-1.5 sm:gap-2 rounded-lg bg-muted/50 px-2 sm:px-3 py-1.5 sm:py-2">
                                <Clock className="h-3 w-3 sm:h-3.5 sm:w-3.5 text-muted-foreground shrink-0" />
                                <div>
                                    <p className="text-[10px] sm:text-xs text-muted-foreground">Daily</p>
                                    <p className="text-xs sm:text-sm font-semibold">{item.hours}h</p>
                                </div>
                            </div>
                        </div>

                        <div className="mt-auto pt-1">
                            {!hasSyllabus ? (
                                <Button
                                    className="w-full"
                                    variant="outline"
                                    disabled={generating}
                                    onClick={handleGenerate}
                                >
                                    {generating ? (
                                        <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating…</>
                                    ) : (
                                        <><Sparkles className="h-4 w-4 mr-2" />Generate Syllabus</>
                                    )}
                                </Button>
                            ) : (
                                <div className="flex gap-2">
                                    <Button
                                        className="flex-1"
                                        onClick={() => onStart(item.skill_id)}
                                    >
                                        <PlayCircle className="h-4 w-4 mr-2" />
                                        {isCompleted ? "Review" : isInProgress ? "Continue" : "Start Course"}
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        title="Regenerate syllabus"
                                        aria-label="Regenerate syllabus"
                                        disabled={generating}
                                        onClick={(e) => { e.stopPropagation(); setConfirmOpen(true); }}
                                        className="shrink-0"
                                    >
                                        {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
                                    </Button>
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col">
                        <div className="flex-1 flex flex-col items-center justify-center text-center py-6">
                            <Sparkles className="h-7 w-7 text-muted-foreground/50 mb-2" />
                            <p className="text-sm text-muted-foreground">No syllabus yet</p>
                            <p className="text-xs text-muted-foreground/70 mt-0.5">Generate one to get started</p>
                        </div>
                        <div className="pb-1">
                            <Button
                                className="w-full"
                                variant="outline"
                                disabled={generating}
                                onClick={handleGenerate}
                            >
                                {generating ? (
                                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating…</>
                                ) : (
                                    <><Sparkles className="h-4 w-4 mr-2" />Generate Syllabus</>
                                )}
                            </Button>
                        </div>
                    </div>
                )}
            </CardContent>

            {/* Regenerate confirmation dialog */}
            <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Regenerate syllabus?</DialogTitle>
                        <DialogDescription>
                            This will replace the existing syllabus for <span className="font-medium text-foreground">{item.skill}</span>. All chapters and progress will be lost. This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2">
                        <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
                        <Button onClick={() => handleGenerate()}>
                            <RotateCw className="h-4 w-4 mr-1.5" />
                            Yes, Regenerate
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    )
}

function CardSkeleton() {
    return (
        <Card className="overflow-hidden border border-border/60">
            <div className="h-0.5 bg-muted" />
            <CardHeader className="pb-3 pt-5">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <Skeleton className="h-9 w-9 rounded-lg" />
                        <Skeleton className="h-5 w-32" />
                    </div>
                    <Skeleton className="h-5 w-20 rounded-full" />
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-1.5">
                    <div className="flex justify-between">
                        <Skeleton className="h-3 w-16" />
                        <Skeleton className="h-3 w-20" />
                    </div>
                    <Skeleton className="h-1.5 w-full rounded-full" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                    <Skeleton className="h-14 rounded-lg" />
                    <Skeleton className="h-14 rounded-lg" />
                </div>
                <Skeleton className="h-9 w-full rounded-md" />
            </CardContent>
        </Card>
    )
}

function StatCard({ icon: Icon, label, value, color }: {
    icon: React.ElementType
    label: string
    value: number
    color: string
}) {
    return (
        <div className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3">
            <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", color)}>
                <Icon className="h-4 w-4" />
            </div>
            <div>
                <p className="text-xl font-bold leading-none">{value}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
            </div>
        </div>
    )
}

export default function SyllabiPage() {
    const [syllabi, setSyllabi] = useState<Syllabus[]>([])
    const [displayList, setDisplayList] = useState<Syllabus[]>([])
    const [loading, setLoading] = useState(true)
    const [searching, setSearching] = useState(false)
    const [search, setSearch] = useState("")
    const navigate = useNavigate()
    const { setPluginName } = useStore((state: any) => state)

    useEffect(() => {
        setPluginName("Courses")
    }, [setPluginName])

    const fetchedRef = useRef(false)

    const fetchSyllabi = useCallback(async () => {
        const { success, data } = await getRequest("/py/syllabi")
        if (success) {
            setSyllabi(data)
            if (!search.trim()) setDisplayList(data)
        }
        setLoading(false)
    }, [search])

    useEffect(() => {
        if (fetchedRef.current) return
        fetchedRef.current = true
        fetchSyllabi()
    }, [fetchSyllabi])

    useEffect(() => {
        const q = search.trim()
        if (!q) {
            setDisplayList(syllabi)
            setSearching(false)
            return
        }
        setSearching(true)
        let cancelled = false
        const timer = setTimeout(async () => {
            const { success, data } = await getRequest(
                `/py/syllabi/search?q=${encodeURIComponent(q)}`
            )
            if (cancelled) return
            if (success) setDisplayList(data)
            setSearching(false)
        }, 350)
        return () => {
            cancelled = true
            clearTimeout(timer)
        }
    }, [search, syllabi])

    function handleSyllabusGenerated() {
        fetchSyllabi()
    }

    // Compute stats
    const total = syllabi.length
    const inProgress = syllabi.filter(s => s.total_tasks > 0 && s.completed_tasks > 0 && s.completed_tasks < s.total_tasks).length
    const completed = syllabi.filter(s => s.total_tasks > 0 && s.completed_tasks === s.total_tasks).length

    return (
        <div className="p-4 sm:p-6 space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Courses</h1>
                    <p className="text-muted-foreground text-sm mt-0.5">All active learning plans</p>
                </div>
                <Button onClick={() => navigate("/enroll")}>
                    <span className="hidden sm:inline">+ New Enrollment</span>
                    <span className="sm:hidden">+ Enroll</span>
                </Button>
            </div>

            {/* LLM selector */}
            <LlmBar />

            {/* Stats row */}
            {!loading && total > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <StatCard icon={GraduationCap} label="Total courses" value={total} color="bg-primary/10 text-primary" />
                    <StatCard icon={CircleDot} label="In progress" value={inProgress} color="bg-indigo-500/10 text-indigo-600" />
                    <StatCard icon={CheckCircle2} label="Completed" value={completed} color="bg-emerald-500/10 text-emerald-600" />
                </div>
            )}

            {/* Search */}
            {!loading && syllabi.length > 0 && (
                <div className="relative max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search courses & chapters..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        aria-label="Search courses and chapters"
                        className="pl-9"
                    />
                    {searching && (
                        <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
                    )}
                </div>
            )}

            {/* Content */}
            {loading ? (
                <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
                    {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
                </div>
            ) : syllabi.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted mb-4">
                        <BookOpen className="h-7 w-7 text-muted-foreground" />
                    </div>
                    <h3 className="font-semibold text-lg">No enrollments yet</h3>
                    <p className="text-muted-foreground text-sm mt-1 mb-5 max-w-xs">
                        Enroll in a subject and we'll generate a personalised syllabus for you.
                    </p>
                    <Button onClick={() => navigate("/enroll")}>+ New Enrollment</Button>
                </Card>
            ) : displayList.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Search className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No courses found</h3>
                    <p className="text-muted-foreground text-sm mt-1">No courses or chapters match "{search}"</p>
                </div>
            ) : (
                <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
                    {displayList.map((item) => (
                        <SyllabusCard
                            key={item.skill_id}
                            item={item}
                            searchQuery={search}
                            onSyllabusGenerated={handleSyllabusGenerated}
                            onStart={(skillId) => navigate(`/syllabi/${skillId}`)}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}
