import { useEffect, useState } from "react"
import { useParams } from "react-router"
import {
    BookOpen, ChevronDown, ChevronRight, FileText,
    PanelLeftClose, PanelLeftOpen,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import axios from "axios"
import { sanitizeHtml } from "@/lib/sanitize"
import { BlockRenderer, type ContentBlock } from "./block-renderer"

interface PublicTask {
    id: number
    day: number
    topic: string
    task: string
    hours: number
    newsletter: string | null
    content_blocks: string | null
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

// ─── Content Panel (right) ────────────────────────────────────────────────────

function ChapterContentPanel({ chapter }: { chapter: PublicTask }) {
    const blocks: ContentBlock[] | null = (() => {
        if (!chapter.content_blocks) return null
        try {
            const parsed = JSON.parse(chapter.content_blocks)
            return Array.isArray(parsed) && parsed.length > 0 ? parsed : null
        } catch { return null }
    })()

    const hasContent = !!chapter.newsletter || !!blocks

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="border-b px-8 py-5 bg-background shrink-0">
                <p className="text-xs text-muted-foreground mb-1">Day {chapter.day} · {chapter.hours}h</p>
                <h2 className="text-2xl font-bold tracking-tight">{chapter.topic}</h2>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto">
                <div className="mx-auto w-full max-w-3xl px-8 py-6 space-y-5">

                    {/* Task */}
                    <div className="rounded-lg border bg-muted/30 px-4 py-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Task</p>
                        <p className="text-sm text-muted-foreground leading-relaxed">{chapter.task}</p>
                    </div>

                    {hasContent ? (
                        <div className="space-y-4">
                            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                <FileText className="h-3 w-3" /> Content
                            </div>
                            {blocks ? (
                                <BlockRenderer blocks={blocks} />
                            ) : (
                                <div
                                    className="prose prose-base max-w-none
                                        prose-headings:text-foreground prose-headings:font-semibold prose-headings:tracking-tight
                                        prose-h1:text-2xl prose-h1:mt-8 prose-h1:mb-4
                                        prose-h2:text-xl prose-h2:mt-6 prose-h2:mb-3 prose-h2:border-b prose-h2:border-border/50 prose-h2:pb-2
                                        prose-h3:text-base prose-h3:mt-5 prose-h3:mb-2
                                        prose-h4:text-sm prose-h4:mt-4 prose-h4:mb-1
                                        prose-p:text-zinc-600 prose-p:leading-7
                                        prose-strong:text-foreground prose-strong:font-semibold
                                        prose-em:text-zinc-600
                                        prose-a:text-primary prose-a:no-underline hover:prose-a:underline prose-a:font-medium
                                        prose-ul:pl-5 prose-ol:pl-5 prose-ul:my-3 prose-ol:my-3
                                        prose-li:text-zinc-600 prose-li:leading-7 prose-li:my-0.5
                                        [&_ul>li::marker]:text-zinc-500 [&_ol>li::marker]:text-zinc-500
                                        prose-code:bg-zinc-100 prose-code:text-zinc-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono prose-code:before:content-none prose-code:after:content-none
                                        [&_pre]:!p-0 [&_pre]:!bg-[#282c34] [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-white/10 [&_pre]:shadow-lg [&_pre]:text-sm
                                        [&_pre_code]:!bg-transparent [&_pre_code]:!p-0 [&_pre_code]:font-mono
                                        prose-blockquote:border-l-4 prose-blockquote:border-primary/40 prose-blockquote:bg-muted/30 prose-blockquote:rounded-r-lg prose-blockquote:py-2 prose-blockquote:px-4 prose-blockquote:not-italic prose-blockquote:text-zinc-600 prose-blockquote:my-4
                                        prose-hr:border-border prose-hr:my-6
                                        prose-table:w-full prose-table:border-collapse prose-table:text-sm
                                        prose-thead:bg-muted/50
                                        prose-th:border prose-th:border-border prose-th:px-4 prose-th:py-2.5 prose-th:text-left prose-th:font-semibold prose-th:text-foreground
                                        prose-td:border prose-td:border-border prose-td:px-4 prose-td:py-2 prose-td:text-zinc-600
                                        prose-tr:even:bg-muted/20
                                        [&_table]:overflow-hidden [&_table]:rounded-lg [&_table]:border [&_table]:border-border"
                                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(chapter.newsletter!) }}
                                />
                            )}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-24 text-center rounded-lg border border-dashed">
                            <FileText className="h-10 w-10 text-muted-foreground mb-3" />
                            <h3 className="font-semibold">No content yet</h3>
                            <p className="text-sm text-muted-foreground mt-1">The owner hasn't generated content for this chapter.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}

// ─── Chapter Nav (left) ───────────────────────────────────────────────────────

function ChapterNav({ syllabus, activeChapterId, onSelectChapter }: {
    syllabus: PublicSyllabus
    activeChapterId: number | null
    onSelectChapter: (chapter: PublicTask) => void
}) {
    const [openMonths, setOpenMonths] = useState<Set<number>>(
        () => new Set(syllabus.months.map((m) => m.month))
    )

    function toggleMonth(month: number) {
        setOpenMonths((prev) => {
            const next = new Set(prev)
            if (next.has(month)) next.delete(month)
            else next.add(month)
            return next
        })
    }

    return (
        <div className="flex-1 overflow-y-auto">
            {syllabus.months.map((month) => (
                <div key={month.month}>
                    <button
                        className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-muted/50 transition-colors"
                        onClick={() => toggleMonth(month.month)}
                    >
                        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Month {month.month}</span>
                        {openMonths.has(month.month)
                            ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
                            : <ChevronRight className="h-3 w-3 text-muted-foreground" />
                        }
                    </button>
                    {openMonths.has(month.month) && month.weeks.map((week) => (
                        <div key={week.week} className="mb-1">
                            <p className="px-4 py-1 text-xs text-muted-foreground/60 font-medium">Week {week.week}</p>
                            {week.tasks.map((chapter) => (
                                <button
                                    key={chapter.id}
                                    onClick={() => onSelectChapter(chapter)}
                                    className={`w-full flex items-start gap-2.5 px-4 py-2 text-left text-sm transition-colors ${
                                        chapter.id === activeChapterId
                                            ? "bg-primary/10 text-primary border-r-2 border-primary"
                                            : "hover:bg-muted/50 text-foreground/80"
                                    }`}
                                >
                                    <span className={`mt-1.5 h-2 w-2 rounded-full flex-shrink-0 ${
                                        (chapter.newsletter || chapter.content_blocks) ? "bg-indigo-400" : "bg-muted-foreground/30"
                                    }`} />
                                    <span className="leading-snug">
                                        <span className="text-xs text-muted-foreground mr-1">D{chapter.day}.</span>
                                        {chapter.topic}
                                    </span>
                                </button>
                            ))}
                        </div>
                    ))}
                </div>
            ))}
        </div>
    )
}

function PageSkeleton() {
    return (
        <div className="flex h-screen overflow-hidden">
            <aside className="w-72 border-r flex flex-col shrink-0">
                <div className="px-4 py-3 border-b space-y-2">
                    <Skeleton className="h-5 w-32" />
                </div>
                <div className="p-4 space-y-2">
                    {[...Array(8)].map((_, i) => <Skeleton key={i} className="h-8 w-full rounded" />)}
                </div>
            </aside>
            <main className="flex-1 p-8 space-y-4">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
            </main>
        </div>
    )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PublicSyllabusPage() {
    const { skillId } = useParams<{ skillId: string }>()
    const [syllabus, setSyllabus] = useState<PublicSyllabus | null>(null)
    const [loading, setLoading] = useState(true)
    const [notFound, setNotFound] = useState(false)
    const [retryable, setRetryable] = useState(false)
    const [activeChapterId, setActiveChapterId] = useState<number | null>(null)
    const [navCollapsed, setNavCollapsed] = useState(false)

    useEffect(() => {
        const controller = new AbortController()
        setLoading(true)
        setNotFound(false)
        setRetryable(false)
        setSyllabus(null)

        async function fetchPublic() {
            try {
                const res = await axios.get(`/py/public/syllabi/${skillId}`, { signal: controller.signal })
                setSyllabus(res.data)
            } catch (err: any) {
                if (axios.isCancel(err)) return
                if (err?.response?.status === 404) setNotFound(true)
                else setRetryable(true)
            } finally {
                if (!controller.signal.aborted) setLoading(false)
            }
        }
        fetchPublic()
        return () => controller.abort()
    }, [skillId])

    const allTasks = syllabus?.months.flatMap((m) => m.weeks.flatMap((w) => w.tasks)) ?? []

    // Auto-select first chapter
    useEffect(() => {
        if (allTasks.length > 0 && activeChapterId === null) {
            setActiveChapterId(allTasks[0].id)
        }
    }, [syllabus])

    const activeChapter = activeChapterId ? allTasks.find((t) => t.id === activeChapterId) ?? null : null

    if (loading) return <PageSkeleton />

    if (retryable) return (
        <div className="flex flex-col items-center justify-center h-screen text-center p-6">
            <BookOpen className="h-12 w-12 text-muted-foreground mb-4" />
            <h1 className="text-2xl font-bold mb-2">Something went wrong</h1>
            <p className="text-muted-foreground mb-4">Could not load this syllabus. Please try again.</p>
            <button className="text-sm text-primary underline" onClick={() => window.location.reload()}>Retry</button>
        </div>
    )

    if (notFound || !syllabus) return (
        <div className="flex flex-col items-center justify-center h-screen text-center p-6">
            <BookOpen className="h-12 w-12 text-muted-foreground mb-4" />
            <h1 className="text-2xl font-bold mb-2">Syllabus not found</h1>
            <p className="text-muted-foreground">This syllabus doesn't exist or public sharing has been disabled.</p>
        </div>
    )

    return (
        <div className="flex overflow-hidden h-screen">

            {/* Left nav panel */}
            <aside className={`flex-shrink-0 border-r flex flex-col h-full overflow-hidden transition-all duration-300 ease-in-out ${navCollapsed ? "w-0 border-r-0" : "w-72"}`}>
                <div className="w-72 flex flex-col h-full">
                    {/* Header */}
                    <div className="flex items-center gap-2 px-4 py-3 border-b shrink-0">
                        <span className="text-sm font-semibold truncate text-foreground/80 flex-1">{syllabus.skill}</span>
                        <Badge variant="outline" className="text-xs shrink-0">Public</Badge>
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => setNavCollapsed(true)}>
                            <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                        </Button>
                    </div>

                    {/* Legend */}
                    <div className="flex items-center gap-3 px-4 py-2 border-b text-xs text-muted-foreground shrink-0">
                        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-indigo-400" />Has content</span>
                        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-muted-foreground/30" />Pending</span>
                    </div>

                    <ChapterNav
                        syllabus={syllabus}
                        activeChapterId={activeChapterId}
                        onSelectChapter={(chapter) => setActiveChapterId(chapter.id)}
                    />
                </div>
            </aside>

            {/* Right content panel */}
            <main className="flex-1 overflow-y-auto flex flex-col">
                {/* Top bar */}
                <div className="flex items-center gap-2 px-4 py-3 border-b shrink-0">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setNavCollapsed((v) => !v)}>
                        {navCollapsed
                            ? <PanelLeftOpen className="h-4 w-4 text-muted-foreground" />
                            : <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                        }
                    </Button>
                    {navCollapsed && <span className="text-sm font-semibold text-foreground/80">{syllabus.skill}</span>}
                    {activeChapter && (
                        <>
                            {navCollapsed && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
                            <span className="text-sm text-muted-foreground truncate">
                                <span className="mr-1">Day {activeChapter.day}.</span>{activeChapter.topic}
                            </span>
                        </>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto">
                    {activeChapter && (
                        <ChapterContentPanel key={activeChapter.id} chapter={activeChapter} />
                    )}
                </div>
            </main>
        </div>
    )
}
