import { useEffect, useRef, useState, useMemo } from "react"
import { useNavigate } from "react-router"
import { BookOpen, Clock, CalendarDays, Mail, TrendingUp, Sparkles, PlayCircle, Loader2, RotateCw, Search } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { getRequest, postRequest } from "@/services"
import useStore from "@/store"

interface Syllabus {
    skill_id: number
    user_id: string
    email: string
    skill: string
    days: number
    hours: number
    created_at: string
    total_tasks: number
    completed_tasks: number
}

function SyllabusCard({ item, onSyllabusGenerated, onStart }: {
    item: Syllabus
    onSyllabusGenerated: (skillId: number) => void
    onStart: (skillId: number) => void
}) {
    const [generating, setGenerating] = useState(false)

    const progress = item.total_tasks > 0
        ? Math.round((item.completed_tasks / item.total_tasks) * 100)
        : 0
    const hasSyllabus = item.total_tasks > 0
    const isCompleted = progress === 100
    const isInProgress = progress > 0 && progress < 100

    async function handleGenerate(e: React.MouseEvent) {
        e.stopPropagation()
        setGenerating(true)
        const { success } = await postRequest("/py/generate-syllabus", {
            skill: item.skill,
        })
        setGenerating(false)
        if (success) onSyllabusGenerated(item.skill_id)
    }

    return (
        <Card className="relative overflow-hidden border border-border/60 bg-card hover:shadow-lg hover:border-border transition-all duration-300 flex flex-col">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-violet-500 via-indigo-500 to-blue-500" />

            <CardHeader className="pb-3 pt-6">
                <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                            <BookOpen className="h-5 w-5" />
                        </div>
                        <h3 className="text-lg font-semibold leading-tight">{item.skill}</h3>
                    </div>
                    {hasSyllabus && (
                        <Badge
                            variant={isCompleted ? "default" : isInProgress ? "secondary" : "outline"}
                            className={
                                isCompleted
                                    ? "bg-emerald-500/15 text-emerald-600 border-emerald-300"
                                    : isInProgress
                                    ? "bg-indigo-500/15 text-indigo-600 border-indigo-300"
                                    : "text-muted-foreground"
                            }
                        >
                            {isCompleted ? "Completed" : isInProgress ? "In Progress" : "Not Started"}
                        </Badge>
                    )}
                </div>
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground mt-1 ml-11">
                    <Mail className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{item.email}</span>
                </div>
            </CardHeader>

            <CardContent className="space-y-4 flex-1 flex flex-col justify-between">
                <div className="space-y-4">
                    {hasSyllabus ? (
                        <div className="space-y-1.5">
                            <div className="flex justify-between text-xs text-muted-foreground">
                                <span className="flex items-center gap-1"><TrendingUp className="h-3 w-3" />Progress</span>
                                <span className="font-medium text-foreground">{item.completed_tasks} / {item.total_tasks} days</span>
                            </div>
                            <Progress value={progress} className="h-2" />
                            <p className="text-right text-xs font-semibold text-primary">{progress}%</p>
                        </div>
                    ) : (
                        <p className="text-xs text-muted-foreground italic">No syllabus yet — generate one to get started.</p>
                    )}

                    <div className="grid grid-cols-2 gap-2">
                        <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2">
                            <CalendarDays className="h-4 w-4 text-muted-foreground" />
                            <div>
                                <p className="text-xs text-muted-foreground">Duration</p>
                                <p className="text-sm font-medium">{item.days} days</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            <div>
                                <p className="text-xs text-muted-foreground">Daily</p>
                                <p className="text-sm font-medium">{item.hours} hr{item.hours !== 1 ? "s" : ""}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* action button */}
                {!hasSyllabus ? (
                    <Button
                        className="w-full mt-2"
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
                    <div className="flex gap-2 mt-2">
                        <Button
                            className="flex-1"
                            onClick={() => onStart(item.skill_id)}
                        >
                            <PlayCircle className="h-4 w-4 mr-2" />
                            {isInProgress ? "Continue" : "Start Course"}
                        </Button>
                        <Button
                            variant="ghost"
                            size="icon"
                            title="Regenerate syllabus"
                            disabled={generating}
                            onClick={handleGenerate}
                        >
                            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
                        </Button>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

function CardSkeleton() {
    return (
        <Card className="overflow-hidden border border-border/60">
            <div className="h-1 bg-muted" />
            <CardHeader className="pb-3 pt-6">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                        <Skeleton className="h-9 w-9 rounded-lg" />
                        <Skeleton className="h-5 w-32" />
                    </div>
                    <Skeleton className="h-5 w-20 rounded-full" />
                </div>
                <Skeleton className="h-4 w-48 ml-11 mt-1" />
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-1.5">
                    <div className="flex justify-between">
                        <Skeleton className="h-3 w-16" />
                        <Skeleton className="h-3 w-20" />
                    </div>
                    <Skeleton className="h-2 w-full rounded-full" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                    <Skeleton className="h-14 rounded-md" />
                    <Skeleton className="h-14 rounded-md" />
                </div>
                <Skeleton className="h-9 w-full rounded-md" />
            </CardContent>
        </Card>
    )
}

export default function SyllabiPage() {
    const [syllabi, setSyllabi] = useState<Syllabus[]>([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState("")
    const navigate = useNavigate()
    const { setPluginName, setPluginInfo } = useStore((state: any) => state)

    const filteredSyllabi = useMemo(() => {
        const q = search.trim().toLowerCase()
        if (!q) return syllabi
        return syllabi.filter((s) => s.skill.toLowerCase().includes(q))
    }, [syllabi, search])

    useEffect(() => {
        setPluginName("Syllabi")
        setPluginInfo("View and manage all learning plans.")
    }, [setPluginName, setPluginInfo])

    const fetchedRef = useRef(false)

    async function fetchSyllabi() {
        const { success, data } = await getRequest("/py/syllabi")
        if (success) setSyllabi(data)
        setLoading(false)
    }

    useEffect(() => {
        if (fetchedRef.current) return
        fetchedRef.current = true
        fetchSyllabi()
    }, [])

    function handleSyllabusGenerated() {
        fetchSyllabi()
    }

    return (
        <div className="p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Syllabi</h1>
                    <p className="text-muted-foreground mt-1">All active learning plans</p>
                </div>
                <Button onClick={() => navigate("/subscribe")}>
                    + New Subscription
                </Button>
            </div>

            {!loading && syllabi.length > 0 && (
                <div className="relative max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Search courses..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="pl-9"
                    />
                </div>
            )}

            {loading ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
                </div>
            ) : syllabi.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-16 text-center border-dashed">
                    <BookOpen className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No subscriptions yet</h3>
                    <p className="text-muted-foreground text-sm mt-1 mb-4">Subscribe to a subject to get started.</p>
                    <Button onClick={() => navigate("/subscribe")}>+ New Subscription</Button>
                </Card>
            ) : filteredSyllabi.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Search className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No courses found</h3>
                    <p className="text-muted-foreground text-sm mt-1">No courses match "{search}"</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {filteredSyllabi.map((item) => (
                        <SyllabusCard
                            key={item.skill_id}
                            item={item}
                            onSyllabusGenerated={handleSyllabusGenerated}
                            onStart={(skillId) => navigate(`/syllabi/${skillId}`)}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}
