import { useEffect, useState } from "react"
import { useParams } from "react-router"
import { GraduationCap, FileText, PanelLeftClose, PanelLeftOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Badge } from "@/components/ui/badge"
import { BlockRenderer, type ContentBlock } from "@/app/plugins/syllabi/block-renderer"
import axios from "axios"

interface PublicDay {
    id: number
    day: number
    topic: string
    task: string
    content_blocks: string | null
    completed: boolean
}

interface PublicPlan {
    id: number
    role: string
    company: string
    created_at: string
}

function DayContentPanel({ day }: { day: PublicDay }) {
    const blocks: ContentBlock[] | null = (() => {
        if (!day.content_blocks) return null
        try {
            const parsed = JSON.parse(day.content_blocks)
            return Array.isArray(parsed) && parsed.length > 0 ? parsed : null
        } catch { return null }
    })()

    return (
        <div className="flex flex-col h-full overflow-hidden">
            <div className="border-b px-4 sm:px-8 py-5 bg-background shrink-0">
                <p className="text-xs text-muted-foreground mb-1">Day {day.day} of 7</p>
                <h2 className="text-xl sm:text-2xl font-bold tracking-tight">{day.topic}</h2>
            </div>
            <div className="flex-1 overflow-y-auto overflow-x-hidden">
                <div className="mx-auto w-full max-w-3xl px-4 sm:px-6 md:px-8 py-6 space-y-5 min-w-0">
                    <div className="rounded-lg border bg-muted/30 px-4 py-3">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">Task</p>
                        <p className="text-sm text-muted-foreground leading-relaxed">{day.task}</p>
                    </div>
                    {blocks ? (
                        <div className="space-y-4">
                            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                                <FileText className="h-3 w-3" /> Content
                            </div>
                            <BlockRenderer blocks={blocks} />
                        </div>
                    ) : (
                        <div className="text-center py-12 text-muted-foreground text-sm">Content not yet generated for this day.</div>
                    )}
                </div>
            </div>
        </div>
    )
}

export default function PublicOnboardingPage() {
    const { planId } = useParams<{ planId: string }>()
    const [plan, setPlan] = useState<PublicPlan | null>(null)
    const [days, setDays] = useState<PublicDay[]>([])
    const [loading, setLoading] = useState(true)
    const [notFound, setNotFound] = useState(false)
    const [activeDayId, setActiveDayId] = useState<number | null>(null)
    const [navOpen, setNavOpen] = useState(false)
    const [navCollapsed, setNavCollapsed] = useState(false)

    useEffect(() => {
        axios.get(`/py/public/onboarding/${planId}`)
            .then(({ data }) => {
                setPlan(data.plan)
                setDays(data.days)
                if (data.days.length > 0) setActiveDayId(data.days[0].id)
            })
            .catch(() => setNotFound(true))
            .finally(() => setLoading(false))
    }, [planId])

    if (loading) return (
        <div className="flex h-screen">
            <aside className="w-72 border-r p-4 space-y-2">
                {[...Array(7)].map((_, i) => <Skeleton key={i} className="h-8 w-full rounded" />)}
            </aside>
            <main className="flex-1 p-8 space-y-4">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
            </main>
        </div>
    )

    if (notFound || !plan) return (
        <div className="flex min-h-screen items-center justify-center text-center px-4">
            <div>
                <GraduationCap className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <h2 className="text-xl font-semibold mb-1">Plan not found</h2>
                <p className="text-sm text-muted-foreground">This onboarding plan is not public or doesn't exist.</p>
            </div>
        </div>
    )

    const activeDay = activeDayId ? days.find(d => d.id === activeDayId) ?? null : null

    return (
        <div className="flex overflow-hidden h-screen" style={{ height: "100dvh" }}>
            {navOpen && <div className="fixed inset-0 bg-black/50 z-40 sm:hidden" onClick={() => setNavOpen(false)} />}

            <aside className={[
                "flex-col h-full overflow-hidden bg-background border-r",
                navOpen ? "fixed left-0 top-0 bottom-0 z-50 flex w-[85vw] shadow-xl" : "hidden",
                navCollapsed ? "sm:hidden" : "sm:relative sm:flex sm:w-72 sm:shrink-0",
            ].join(" ")}>
                <div className="flex items-center gap-2 px-4 py-3 border-b shrink-0">
                    <GraduationCap className="h-4 w-4 text-primary shrink-0" />
                    <span className="text-sm font-semibold truncate flex-1">{plan.role}</span>
                    <Badge variant="outline" className="text-xs shrink-0">{plan.company}</Badge>
                    <Button variant="ghost" size="icon" className="h-7 w-7 hidden sm:flex" onClick={() => setNavCollapsed(true)}>
                        <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 flex sm:hidden" onClick={() => setNavOpen(false)}>
                        <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
                    </Button>
                </div>
                <div className="flex-1 overflow-y-auto">
                    {days.map((day) => (
                        <button key={day.id} onClick={() => { setActiveDayId(day.id); setNavOpen(false) }}
                            className={`w-full flex items-start gap-2.5 px-4 py-2.5 text-left text-sm transition-colors ${
                                day.id === activeDayId ? "bg-primary/10 text-primary border-r-2 border-primary" : "hover:bg-muted/50 text-foreground/80"
                            }`}>
                            <span className="mt-1.5 h-2 w-2 rounded-full flex-shrink-0 bg-muted-foreground/30" />
                            <span className="leading-snug">
                                <span className="text-xs text-muted-foreground mr-1">D{day.day}.</span>
                                {day.topic}
                            </span>
                        </button>
                    ))}
                </div>
            </aside>

            <main className="flex-1 w-0 min-w-0 flex flex-col overflow-hidden">
                <div className="flex items-center gap-2 px-3 sm:px-4 py-3 border-b shrink-0">
                    <Button variant="ghost" size="icon" className="h-7 w-7 flex sm:hidden shrink-0" onClick={() => setNavOpen(true)}>
                        <PanelLeftOpen className="h-4 w-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-7 w-7 hidden sm:flex shrink-0" onClick={() => setNavCollapsed(v => !v)}>
                        {navCollapsed ? <PanelLeftOpen className="h-4 w-4 text-muted-foreground" /> : <PanelLeftClose className="h-4 w-4 text-muted-foreground" />}
                    </Button>
                    {navCollapsed && <span className="text-sm font-semibold truncate">{plan.role}</span>}
                    {activeDay && (
                        <span className="text-sm text-muted-foreground truncate">
                            Day {activeDay.day}. {activeDay.topic}
                        </span>
                    )}
                </div>
                <div className="flex-1 overflow-hidden">
                    {activeDay ? <DayContentPanel day={activeDay} /> : null}
                </div>
            </main>
        </div>
    )
}
