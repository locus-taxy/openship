import { useEffect, useState } from "react"
import { useParams } from "react-router"
import {
    BookOpen, Clock, ChevronDown, ChevronRight, FileText,
} from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import axios from "axios"
import { sanitizeHtml } from "@/lib/sanitize"

interface PublicTask {
    id: number
    day: number
    topic: string
    task: string
    hours: number
    newsletter: string | null
}

interface PublicWeek {
    week: number
    tasks: PublicTask[]
}

interface PublicMonth {
    month: number
    weeks: PublicWeek[]
}

interface PublicSyllabus {
    skill_id: number
    skill: string
    days: number
    hours: number
    created_at: string
    months: PublicMonth[]
}

function ChapterRow({ chapter }: { chapter: PublicTask }) {
    const [expanded, setExpanded] = useState(false)

    return (
        <div className="rounded-lg border border-border bg-card">
            <div className="flex w-full items-center gap-3 px-4 py-3">
                <button
                    className="flex-1 text-left text-sm font-medium leading-snug"
                    onClick={() => setExpanded((v) => !v)}
                >
                    <span className="text-muted-foreground mr-2">Day {chapter.day}.</span>
                    {chapter.topic}
                </button>
                <div className="flex items-center gap-2 shrink-0">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {chapter.hours}h
                    </span>
                    <button onClick={() => setExpanded((v) => !v)}>
                        {expanded
                            ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            : <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        }
                    </button>
                </div>
            </div>

            {expanded && (
                <div className="border-t border-border/50">
                    <div className="px-4 py-3 bg-muted/20">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Task</p>
                        <p className="text-sm text-muted-foreground leading-relaxed">{chapter.task}</p>
                    </div>
                    {chapter.newsletter && (
                        <div className="border-t border-border/50">
                            <div className="px-4 pt-3 pb-1">
                                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                                    <FileText className="h-3 w-3" /> Newsletter Content
                                </p>
                            </div>
                            <div
                                className="px-4 py-3 prose prose-sm max-w-none text-foreground overflow-auto max-h-[500px]"
                                dangerouslySetInnerHTML={{ __html: sanitizeHtml(chapter.newsletter) }}
                            />
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

function WeekSection({ week, selected, onSelect }: {
    week: PublicWeek
    selected: boolean
    onSelect: (w: number | null) => void
}) {
    const [open, setOpen] = useState(true)

    return (
        <div className="space-y-2">
            <div className="flex w-full items-center justify-between py-1">
                <button
                    className="flex items-center gap-2 text-left"
                    onClick={() => setOpen((v) => !v)}
                >
                    <span className="text-sm font-semibold text-foreground/80">Week {week.week}</span>
                    <span className="text-xs text-muted-foreground">{week.tasks.length} days</span>
                    {open
                        ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    }
                </button>
                <Button
                    size="sm"
                    variant={selected ? "default" : "outline"}
                    className="h-6 px-2 text-xs"
                    onClick={() => onSelect(selected ? null : week.week)}
                >
                    {selected ? "Showing week" : "View week"}
                </Button>
            </div>
            {open && (
                <div className="space-y-2 pl-1">
                    {week.tasks.map((chapter) => (
                        <ChapterRow key={chapter.id} chapter={chapter} />
                    ))}
                </div>
            )}
        </div>
    )
}

function MonthSection({ month, selectedWeek, onSelectWeek }: {
    month: PublicMonth
    selectedWeek: number | null
    onSelectWeek: (w: number | null) => void
}) {
    const totalTasks = month.weeks.reduce((acc, w) => acc + w.tasks.length, 0)
    const visibleWeeks = selectedWeek !== null
        ? month.weeks.filter((w) => w.week === selectedWeek)
        : month.weeks

    return (
        <Card className="overflow-hidden">
            <CardHeader className="pb-3 bg-muted/30">
                <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
                            {month.month}
                        </div>
                        <span className="font-semibold">Month {month.month}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{totalTasks} days</span>
                </div>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
                {visibleWeeks.map((week) => (
                    <WeekSection
                        key={week.week}
                        week={week}
                        selected={selectedWeek === week.week}
                        onSelect={onSelectWeek}
                    />
                ))}
                {visibleWeeks.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No weeks match the current filter.</p>
                )}
            </CardContent>
        </Card>
    )
}

function PageSkeleton() {
    return (
        <div className="max-w-4xl mx-auto p-6 space-y-6">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-9 w-full rounded-lg" />
            {[1, 2].map((i) => (
                <Card key={i} className="overflow-hidden">
                    <CardHeader className="bg-muted/30">
                        <div className="flex items-center gap-2">
                            <Skeleton className="h-7 w-7 rounded-md" />
                            <Skeleton className="h-5 w-24" />
                        </div>
                    </CardHeader>
                    <CardContent className="pt-4 space-y-2">
                        {[1, 2, 3].map((j) => (
                            <Skeleton key={j} className="h-11 w-full rounded-lg" />
                        ))}
                    </CardContent>
                </Card>
            ))}
        </div>
    )
}

export default function PublicSyllabusPage() {
    const { skillId } = useParams<{ skillId: string }>()
    const [syllabus, setSyllabus] = useState<PublicSyllabus | null>(null)
    const [loading, setLoading] = useState(true)
    const [notFound, setNotFound] = useState(false)
    const [retryable, setRetryable] = useState(false)
    const [selectedMonth, setSelectedMonth] = useState<number | null>(null)
    const [selectedWeek, setSelectedWeek] = useState<number | null>(null)

    useEffect(() => {
        setLoading(true)
        setNotFound(false)
        setRetryable(false)
        setSyllabus(null)
        async function fetchPublic() {
            try {
                const res = await axios.get(`/py/public/syllabi/${skillId}`)
                setSyllabus(res.data)
            } catch (err: any) {
                const status = err?.response?.status
                if (status === 404) {
                    setNotFound(true)
                } else {
                    setRetryable(true)
                }
            } finally {
                setLoading(false)
            }
        }
        fetchPublic()
    }, [skillId])

    function handleSelectMonth(m: number) {
        if (selectedMonth === m) {
            setSelectedMonth(null)
            setSelectedWeek(null)
        } else {
            setSelectedMonth(m)
            setSelectedWeek(null)
        }
    }

    if (loading) return <PageSkeleton />

    if (retryable) {
        return (
            <div className="max-w-4xl mx-auto p-6 flex flex-col items-center justify-center min-h-[60vh] text-center">
                <BookOpen className="h-12 w-12 text-muted-foreground mb-4" />
                <h1 className="text-2xl font-bold mb-2">Something went wrong</h1>
                <p className="text-muted-foreground mb-4">
                    Could not load this syllabus. Please try again in a moment.
                </p>
                <button
                    className="text-sm text-primary underline"
                    onClick={() => window.location.reload()}
                >
                    Retry
                </button>
            </div>
        )
    }

    if (notFound || !syllabus) {
        return (
            <div className="max-w-4xl mx-auto p-6 flex flex-col items-center justify-center min-h-[60vh] text-center">
                <BookOpen className="h-12 w-12 text-muted-foreground mb-4" />
                <h1 className="text-2xl font-bold mb-2">Syllabus not found</h1>
                <p className="text-muted-foreground">
                    This syllabus doesn't exist or the owner has disabled public sharing.
                </p>
            </div>
        )
    }

    const allTasks = syllabus.months.flatMap((m) => m.weeks.flatMap((w) => w.tasks))
    const visibleMonths = selectedMonth !== null
        ? syllabus.months.filter((m) => m.month === selectedMonth)
        : syllabus.months

    return (
        <div className="max-w-4xl mx-auto p-6 space-y-6">
            {/* header */}
            <div className="space-y-3">
                <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <BookOpen className="h-5 w-5" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold tracking-tight">{syllabus.skill}</h1>
                        <p className="text-sm text-muted-foreground">
                            {syllabus.days} days · {syllabus.hours} hr/day
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3 flex-wrap text-sm text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                        <Clock className="h-4 w-4" />
                        {allTasks.length} total chapters
                    </span>
                    <Badge variant="outline">Read-only · Public view</Badge>
                </div>
            </div>

            {/* month navigation tabs */}
            {syllabus.months.length > 1 && (
                <div className="flex flex-wrap gap-2">
                    <Button
                        size="sm"
                        variant={selectedMonth === null ? "default" : "outline"}
                        className="h-8 text-xs"
                        onClick={() => { setSelectedMonth(null); setSelectedWeek(null) }}
                    >
                        All months
                    </Button>
                    {syllabus.months.map((m) => (
                        <Button
                            key={m.month}
                            size="sm"
                            variant={selectedMonth === m.month ? "default" : "outline"}
                            className="h-8 text-xs"
                            onClick={() => handleSelectMonth(m.month)}
                        >
                            Month {m.month}
                        </Button>
                    ))}
                </div>
            )}

            {/* content */}
            {syllabus.months.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-16 text-center border-dashed">
                    <BookOpen className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No chapters available yet</h3>
                </Card>
            ) : (
                <div className="space-y-4">
                    {visibleMonths.map((month) => (
                        <MonthSection
                            key={month.month}
                            month={month}
                            selectedWeek={selectedWeek}
                            onSelectWeek={(w) => setSelectedWeek(w)}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}
