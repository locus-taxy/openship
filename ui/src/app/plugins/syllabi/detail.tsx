import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router"
import {
    ArrowLeft, BookOpen, CheckCircle2, Circle, Clock,
    FileText, ChevronDown, ChevronRight, Sparkles, Loader2, Send, Eye,
    Globe, Copy, Check,
} from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Progress } from "@/components/ui/progress"
import { getRequest, postRequest } from "@/services"
import api from "@/services"
import useStore from "@/store"
import { sanitizeHtml } from "@/lib/sanitize"

interface Chapter {
    id: number
    day: number
    topic: string
    task: string
    hours: number
    completed: boolean
    has_content: boolean
}

interface Week {
    week: number
    tasks: Chapter[]
}

interface Month {
    month: number
    weeks: Week[]
}

interface SyllabusDetail {
    skill_id: number
    skill: string
    email: string
    days: number
    hours: number
    share_enabled: boolean
    created_at: string
    months: Month[]
}

function ChapterRow({ chapter, onContentGenerated }: {
    chapter: Chapter
    onContentGenerated: (taskId: number) => void
}) {
    const [expanded, setExpanded] = useState(false)
    const [generating, setGenerating] = useState(false)
    const [hasContent, setHasContent] = useState(chapter.has_content)
    const [newsletterHtml, setNewsletterHtml] = useState<string | null>(null)
    const [loadingContent, setLoadingContent] = useState(false)
    const [sending, setSending] = useState(false)
    const [sent, setSent] = useState(chapter.completed)

    async function handleGenerate(e: React.MouseEvent) {
        e.stopPropagation()
        setGenerating(true)
        const { success } = await postRequest("/py/generate-content/chapter", { task_id: chapter.id })
        setGenerating(false)
        if (success) {
            setHasContent(true)
            onContentGenerated(chapter.id)
        }
    }

    async function handleExpand() {
        setExpanded((v) => !v)
        // load content on first expand if available
        if (!expanded && hasContent && !newsletterHtml) {
            setLoadingContent(true)
            const { success, data } = await getRequest(`/py/chapter/${chapter.id}`)
            if (success) setNewsletterHtml(data.newsletter)
            setLoadingContent(false)
        }
    }

    async function handleSendEmail() {
        setSending(true)
        const { success } = await postRequest("/py/send-email/chapter", { task_id: chapter.id })
        setSending(false)
        if (success) setSent(true)
    }

    return (
        <div
            className={`rounded-lg border transition-colors ${
                sent
                    ? "border-emerald-200 bg-emerald-50/40 dark:border-emerald-900/50 dark:bg-emerald-950/20"
                    : "border-border bg-card"
            }`}
        >
            <div className="flex w-full items-center gap-3 px-4 py-3">
                <button onClick={handleExpand} className="shrink-0">
                    {sent
                        ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        : <Circle className="h-4 w-4 text-muted-foreground" />
                    }
                </button>

                <button className="flex-1 text-left text-sm font-medium leading-snug" onClick={handleExpand}>
                    <span className="text-muted-foreground mr-2">Day {chapter.day}.</span>
                    {chapter.topic}
                </button>

                <div className="flex items-center gap-2 shrink-0">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {chapter.hours}h
                    </span>

                    {hasContent ? (
                        <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2 text-xs gap-1 text-indigo-500 border-indigo-300 hover:text-indigo-600"
                            onClick={handleExpand}
                        >
                            <Eye className="h-3 w-3" />
                            {expanded ? "Hide" : "View"}
                        </Button>
                    ) : (
                        <Button
                            size="sm"
                            variant="outline"
                            className="h-7 px-2 text-xs gap-1"
                            disabled={generating}
                            onClick={handleGenerate}
                        >
                            {generating
                                ? <><Loader2 className="h-3 w-3 animate-spin" />Generating</>
                                : <><Sparkles className="h-3 w-3" />Generate</>
                            }
                        </Button>
                    )}

                    <button onClick={handleExpand}>
                        {expanded
                            ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            : <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        }
                    </button>
                </div>
            </div>

            {expanded && (
                <div className="border-t border-border/50">
                    {/* task description */}
                    <div className="px-4 py-3 bg-muted/20">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Task</p>
                        <p className="text-sm text-muted-foreground leading-relaxed">{chapter.task}</p>
                    </div>

                    {/* newsletter content */}
                    {hasContent && (
                        <div className="border-t border-border/50">
                            <div className="px-4 pt-3 pb-1">
                                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                                    <FileText className="h-3 w-3" /> Newsletter Content
                                </p>
                            </div>

                            {loadingContent ? (
                                <div className="px-4 py-6 space-y-2">
                                    <div className="h-3 bg-muted rounded animate-pulse w-3/4" />
                                    <div className="h-3 bg-muted rounded animate-pulse w-full" />
                                    <div className="h-3 bg-muted rounded animate-pulse w-5/6" />
                                    <div className="h-3 bg-muted rounded animate-pulse w-2/3" />
                                </div>
                            ) : newsletterHtml ? (
                                <>
                                    <div
                                        className="px-4 py-3 text-sm text-foreground leading-relaxed overflow-auto max-h-[500px] border-b border-border/50
                                            [&_h1]:text-base [&_h1]:font-semibold [&_h1]:mb-2 [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mb-1
                                            [&_p]:text-muted-foreground [&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal
                                            [&_ol]:pl-4 [&_li]:text-muted-foreground [&_li]:mb-0.5 [&_a]:text-primary [&_a]:underline"
                                        dangerouslySetInnerHTML={{ __html: sanitizeHtml(newsletterHtml) }}
                                    />
                                    <div className="px-4 py-3 flex items-center justify-between gap-3">
                                        {sent ? (
                                            <span className="flex items-center gap-1.5 text-sm text-emerald-600 font-medium">
                                                <CheckCircle2 className="h-4 w-4" /> Email sent
                                            </span>
                                        ) : (
                                            <p className="text-xs text-muted-foreground">Ready to send to enrollee's inbox.</p>
                                        )}
                                        <Button
                                            size="sm"
                                            disabled={sending || sent}
                                            onClick={handleSendEmail}
                                            className={sent ? "bg-emerald-600 hover:bg-emerald-700" : ""}
                                        >
                                            {sending ? (
                                                <><Loader2 className="h-4 w-4 mr-1.5 animate-spin" />Sending…</>
                                            ) : sent ? (
                                                <><CheckCircle2 className="h-4 w-4 mr-1.5" />Sent</>
                                            ) : (
                                                <><Send className="h-4 w-4 mr-1.5" />Send Email</>
                                            )}
                                        </Button>
                                    </div>
                                </>
                            ) : null}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

function WeekSection({ week, onContentGenerated }: {
    week: Week
    onContentGenerated: (taskId: number) => void
}) {
    const [open, setOpen] = useState(true)
    const completedCount = week.tasks.filter((t) => t.completed).length

    return (
        <div className="space-y-2">
            <button
                className="flex w-full items-center justify-between py-1 text-left"
                onClick={() => setOpen((v) => !v)}
            >
                <span className="text-sm font-semibold text-foreground/80">Week {week.week}</span>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">{completedCount}/{week.tasks.length} done</span>
                    {open
                        ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    }
                </div>
            </button>
            {open && (
                <div className="space-y-2 pl-1">
                    {week.tasks.map((chapter) => (
                        <ChapterRow key={chapter.id} chapter={chapter} onContentGenerated={onContentGenerated} />
                    ))}
                </div>
            )}
        </div>
    )
}

function MonthSection({ month, onContentGenerated }: {
    month: Month
    onContentGenerated: (taskId: number) => void
}) {
    const allTasks = month.weeks.flatMap((w) => w.tasks)
    const completedCount = allTasks.filter((t) => t.completed).length
    const progress = allTasks.length > 0 ? Math.round((completedCount / allTasks.length) * 100) : 0

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
                    <div className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground">{completedCount}/{allTasks.length} days</span>
                        <Badge variant="outline" className="text-xs">{progress}%</Badge>
                    </div>
                </div>
                <Progress value={progress} className="h-1.5 mt-2" />
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
                {month.weeks.map((week) => (
                    <WeekSection
                        key={week.week}
                        week={week}
                        onContentGenerated={onContentGenerated}
                    />
                ))}
            </CardContent>
        </Card>
    )
}

function DetailSkeleton() {
    return (
        <div className="p-6 space-y-6">
            <div className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded" />
                <Skeleton className="h-7 w-48" />
            </div>
            {[1, 2].map((i) => (
                <Card key={i} className="overflow-hidden">
                    <CardHeader className="bg-muted/30">
                        <div className="flex items-center gap-2">
                            <Skeleton className="h-7 w-7 rounded-md" />
                            <Skeleton className="h-5 w-24" />
                        </div>
                        <Skeleton className="h-1.5 w-full mt-2 rounded-full" />
                    </CardHeader>
                    <CardContent className="pt-4 space-y-2">
                        {[1, 2, 3, 4].map((j) => (
                            <Skeleton key={j} className="h-11 w-full rounded-lg" />
                        ))}
                    </CardContent>
                </Card>
            ))}
        </div>
    )
}

export default function SyllabusDetailPage() {
    const { skillId } = useParams<{ skillId: string }>()
    const navigate = useNavigate()
    const [detail, setDetail] = useState<SyllabusDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const { setPluginName } = useStore((state: any) => state)
    const [shareEnabled, setShareEnabled] = useState(false)
    const [togglingShare, setTogglingShare] = useState(false)
    const [copied, setCopied] = useState(false)
    

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        async function fetchDetail() {
            const { success, data } = await getRequest(`/py/syllabi/${skillId}`)
            if (cancelled) return
            if (success) {
                setDetail(data)
                setShareEnabled(data.share_enabled ?? false)
                setPluginName(data.skill)
            }
            setLoading(false)
        }
        fetchDetail()
        return () => { cancelled = true }
    }, [skillId, setPluginName])


    const allTasks = detail?.months.flatMap((m) => m.weeks.flatMap((w) => w.tasks)) ?? []
    const completedCount = allTasks.filter((t) => t.completed).length
    const overallProgress = allTasks.length > 0 ? Math.round((completedCount / allTasks.length) * 100) : 0

    // called when a chapter's content is generated — update local state without full refetch
    function handleContentGenerated(taskId: number) {
        setDetail((prev) => {
            if (!prev) return prev
            return {
                ...prev,
                months: prev.months.map((m) => ({
                    ...m,
                    weeks: m.weeks.map((w) => ({
                        ...w,
                        tasks: w.tasks.map((t) => t.id === taskId ? { ...t, has_content: true } : t),
                    })),
                })),
            }
        })
    }

    async function handleToggleShare() {
        setTogglingShare(true)
        const nextValue = !shareEnabled
        try {
            await api.patch(`/py/syllabi/${skillId}/share?enable=${nextValue}`)
            setShareEnabled(nextValue)
        } catch {
            // leave state unchanged on error
        } finally {
            setTogglingShare(false)
        }
    }

    async function handleCopyLink() {
        const url = `${window.location.origin}/public/syllabi/${skillId}`
        await navigator.clipboard.writeText(url)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    if (loading) return <DetailSkeleton />

    if (!detail) return (
        <div className="p-6">
            <Button variant="ghost" size="sm" onClick={() => navigate("/syllabi")}>
                <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
            <p className="mt-4 text-muted-foreground">Syllabus not found.</p>
        </div>
    )

    return (
        <div className="p-6 space-y-6">
            {/* header */}
            <div className="space-y-3">
                <Button variant="ghost" size="sm" className="-ml-2" onClick={() => navigate("/syllabi")}>
                    <ArrowLeft className="h-4 w-4 mr-1" /> All Syllabi
                </Button>
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                            <BookOpen className="h-5 w-5" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold tracking-tight">{detail.skill}</h1>
                            <p className="text-sm text-muted-foreground">{detail.email}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                            <Clock className="h-4 w-4" />
                            {detail.hours} hr/day · {detail.days} days
                        </span>
                        <Badge variant="outline" className="text-sm font-semibold">
                            {overallProgress}% complete
                        </Badge>
                    </div>
                </div>
                <div className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Overall progress</span>
                        <span>{completedCount} / {allTasks.length} chapters done</span>
                    </div>
                    <Progress value={overallProgress} className="h-2" />
                </div>

                {/* share controls */}
                <div className="flex items-center justify-between rounded-lg border border-border bg-muted/20 px-4 py-3">
                    <div className="flex items-center gap-3">
                        <div className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
                            shareEnabled
                                ? "bg-emerald-500/15 text-emerald-500"
                                : "bg-muted text-muted-foreground"
                        }`}>
                            <Globe className="h-4 w-4" />
                        </div>
                        <div>
                            <p className="text-sm font-medium leading-none">Public page</p>
                            <p className="text-xs text-muted-foreground mt-1">
                                {shareEnabled
                                    ? "Anyone with the link can view this syllabus"
                                    : "Share a read-only view with anyone"}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {shareEnabled && (
                            <Button
                                size="sm"
                                variant="outline"
                                className="h-7 gap-1.5 text-xs"
                                onClick={handleCopyLink}
                            >
                                {copied
                                    ? <><Check className="h-3 w-3 text-emerald-500" />Copied</>
                                    : <><Copy className="h-3 w-3" />Copy link</>
                                }
                            </Button>
                        )}
                        <Button
                            size="sm"
                            variant={shareEnabled ? "ghost" : "default"}
                            className={`h-7 text-xs ${shareEnabled ? "text-muted-foreground hover:text-destructive hover:bg-destructive/10" : ""}`}
                            disabled={togglingShare}
                            onClick={handleToggleShare}
                        >
                            {togglingShare
                                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                : shareEnabled ? "Disable" : "Enable"
                            }
                        </Button>
                    </div>
                </div>
            </div>

            {/* months */}
            {detail.months.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-16 text-center border-dashed">
                    <BookOpen className="h-10 w-10 text-muted-foreground mb-3" />
                    <h3 className="font-semibold text-lg">No chapters yet</h3>
                    <p className="text-muted-foreground text-sm mt-1">Go back and generate a syllabus first.</p>
                    <Button variant="outline" className="mt-4" onClick={() => navigate("/syllabi")}>
                        <ArrowLeft className="h-4 w-4 mr-1" /> Back to Syllabi
                    </Button>
                </Card>
            ) : (
                <div className="space-y-4">
                    {detail.months.map((month) => (
                        <MonthSection
                            key={month.month}
                            month={month}
                            onContentGenerated={handleContentGenerated}
                        />
                    ))}
                </div>
            )}
        </div>
    )
}
