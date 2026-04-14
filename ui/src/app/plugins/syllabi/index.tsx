import { useEffect, useRef, useState, useCallback } from "react"
import { useNavigate } from "react-router"
import { BookOpen, Clock, CalendarDays, TrendingUp, Sparkles, PlayCircle, Loader2, RotateCw, Search, FileText } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { getRequest, postRequest } from "@/services"
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
    const chapters = item.matching_chapters ?? []
    const hasMatchingChapters = searchQuery.trim() !== "" && chapters.length > 0

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
                        <h3 className="text-lg font-semibold leading-tight line-clamp-2 min-h-[2.75rem]">{item.skill}</h3>
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
            </CardHeader>

            <CardContent className="flex-1 flex flex-col">
                {hasSyllabus || hasMatchingChapters ? (
                    <div className="space-y-4 flex-1 flex flex-col">
                        {hasSyllabus && (
                            <div className="space-y-1.5">
                                <div className="flex justify-between text-xs text-muted-foreground">
                                    <span className="flex items-center gap-1"><TrendingUp className="h-3 w-3" />Progress</span>
                                    <span className="font-medium text-foreground">{item.completed_tasks} / {item.total_tasks} days</span>
                                </div>
                                <Progress value={progress} className="h-2" />
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

                        <div className="mt-auto pt-2">
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
                                        {isInProgress ? "Continue" : "Start Course"}
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        title="Regenerate syllabus"
                                        aria-label="Regenerate syllabus"
                                        disabled={generating}
                                        onClick={handleGenerate}
                                    >
                                        {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCw className="h-4 w-4" />}
                                    </Button>
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col">
                        <div className="flex-1 flex flex-col items-center justify-center text-center py-4">
                            <BookOpen className="h-8 w-8 text-muted-foreground mb-2" />
                            <p className="text-sm text-muted-foreground italic">No syllabus yet — generate one to get started.</p>
                        </div>
                        <div className="mt-auto pt-2">
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
    const [displayList, setDisplayList] = useState<Syllabus[]>([])
    const [loading, setLoading] = useState(true)
    const [searching, setSearching] = useState(false)
    const [search, setSearch] = useState("")
    const navigate = useNavigate()
    const { setPluginName } = useStore((state: any) => state)

    useEffect(() => {
        setPluginName("Syllabi")
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

    return (
        <div className="p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Syllabi</h1>
                    <p className="text-muted-foreground mt-1">All active learning plans</p>
                </div>
                <Button onClick={() => navigate("/enroll")}>
                    + New Enrollment
                </Button>
            </div>

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

            {loading ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)}
                </div>
            ) : syllabi.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-16 text-center border-dashed">
                    <BookOpen className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No enrollments yet</h3>
                    <p className="text-muted-foreground text-sm mt-1 mb-4">Enroll in a subject to get started.</p>
                    <Button onClick={() => navigate("/enroll")}>+ New Enrollment</Button>
                </Card>
            ) : displayList.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Search className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No courses found</h3>
                    <p className="text-muted-foreground text-sm mt-1">No courses or chapters match "{search}"</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
