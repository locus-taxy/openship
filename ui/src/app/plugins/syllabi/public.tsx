import { useEffect, useRef, useState } from "react"
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
import hljs from "highlight.js"
import "highlight.js/styles/atom-one-dark.css"

// ─── Block rendering (for structured content_blocks) ─────────────────────────

type BlockType = "heading" | "paragraph" | "code" | "bullet_list" | "numbered_list" | "table" | "note" | "quote" | "divider" | "diagram"

interface ContentBlock {
    type: BlockType
    content?: string
    level?: number
    language?: string
    items?: string[]
    headers?: string[]
    rows?: string[][]
}

function InlineText({ text }: { text: string }) {
    const parts = text.split(/(`[^`]+`)/g)
    return (
        <>
            {parts.map((part, i) => {
                if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
                    return <code key={i} className="bg-zinc-100 text-zinc-800 px-1.5 py-0.5 rounded text-[0.82em] font-mono">{part.slice(1, -1)}</code>
                const boldParts = part.split(/(\*\*[^*]+\*\*)/g)
                if (boldParts.length > 1)
                    return boldParts.map((bp, j) =>
                        bp.startsWith("**") && bp.endsWith("**") && bp.length > 4
                            ? <strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>
                            : <span key={`${i}-${j}`}>{bp}</span>
                    )
                return <span key={i}>{part}</span>
            })}
        </>
    )
}

function PublicCodeBlock({ code, language }: { code: string; language: string }) {
    const ref = useRef<HTMLElement>(null)
    const [copied, setCopied] = useState(false)

    useEffect(() => {
        if (!ref.current) return
        ref.current.textContent = code
        try {
            if (language) ref.current.innerHTML = hljs.highlight(code, { language }).value
            else hljs.highlightElement(ref.current)
        } catch { hljs.highlightElement(ref.current) }
        ref.current.classList.add("hljs")
    }, [code, language])

    const lines = code.split("\n")
    if (lines[lines.length - 1] === "") lines.pop()

    async function handleCopy() {
        try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* denied */ }
    }

    const ICON_COPY = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`
    const ICON_CHECK = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`

    return (
        <div className="relative rounded-xl border border-white/10 bg-[#282c34] text-sm shadow-lg overflow-hidden">
            <button onClick={handleCopy} title="Copy code"
                dangerouslySetInnerHTML={{ __html: copied ? ICON_CHECK : ICON_COPY }}
                style={{ position: "absolute", top: 10, right: 10, background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, padding: "5px 8px", cursor: "pointer", color: copied ? "#4ade80" : "#9da5b4", display: "flex", alignItems: "center", justifyContent: "center" }}
            />
            <div className="flex overflow-x-auto">
                <div className="flex flex-col shrink-0 select-none text-right px-3 py-4 text-[#636d83] text-xs leading-[1.6] border-r border-white/[0.08] min-w-[2.5rem]">
                    {lines.map((_, i) => <span key={i}>{i + 1}</span>)}
                </div>
                <div className="flex-1 overflow-x-auto px-5 py-4 min-w-0">
                    <code ref={ref} className="font-mono text-xs leading-[1.6] whitespace-pre block" />
                </div>
            </div>
        </div>
    )
}

function BlockItem({ block }: { block: ContentBlock }) {
    switch (block.type) {
        case "heading": {
            const text = block.content ?? ""
            if (block.level === 1) return <h1 className="text-2xl font-bold tracking-tight text-foreground mt-6 mb-3"><InlineText text={text} /></h1>
            if (block.level === 3) return <h3 className="text-base font-semibold text-foreground mt-4 mb-1.5"><InlineText text={text} /></h3>
            return <h2 className="text-xl font-semibold text-foreground mt-5 mb-2 border-b border-border/50 pb-2"><InlineText text={text} /></h2>
        }
        case "paragraph": return <p className="text-zinc-600 leading-7"><InlineText text={block.content ?? ""} /></p>
        case "code": return <PublicCodeBlock code={block.content ?? ""} language={block.language ?? ""} />
        case "diagram": return <PublicCodeBlock code={block.content ?? ""} language="plaintext" />
        case "bullet_list": return <ul className="list-disc pl-5 space-y-1 text-zinc-600">{block.items?.map((item, i) => <li key={i} className="leading-7"><InlineText text={item} /></li>)}</ul>
        case "numbered_list": return <ol className="list-decimal pl-5 space-y-1 text-zinc-600">{block.items?.map((item, i) => <li key={i} className="leading-7"><InlineText text={item} /></li>)}</ol>
        case "table": return (
            <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full border-collapse text-sm">
                    <thead className="bg-muted/50"><tr>{block.headers?.map((h, i) => <th key={i} className="border border-border px-4 py-2.5 text-left font-semibold text-foreground"><InlineText text={h} /></th>)}</tr></thead>
                    <tbody>{block.rows?.map((row, i) => <tr key={i} className={i % 2 === 1 ? "bg-muted/20" : ""}>{row.map((cell, j) => <td key={j} className="border border-border px-4 py-2 text-zinc-600"><InlineText text={cell} /></td>)}</tr>)}</tbody>
                </table>
            </div>
        )
        case "note": return <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3"><p className="text-sm text-foreground/80 leading-7"><InlineText text={block.content ?? ""} /></p></div>
        case "quote": return <blockquote className="border-l-4 border-primary/40 bg-muted/30 rounded-r-lg py-2 px-4 text-zinc-600 italic"><InlineText text={block.content ?? ""} /></blockquote>
        case "divider": return <hr className="border-border my-2" />
        default: return null
    }
}

function BlockRenderer({ blocks }: { blocks: ContentBlock[] }) {
    return <div className="space-y-4">{blocks.map((block, i) => <BlockItem key={i} block={block} />)}</div>
}

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
    const proseRef = useRef<HTMLDivElement>(null)

    const blocks: ContentBlock[] | null = (() => {
        if (!chapter.content_blocks) return null
        try {
            const parsed = JSON.parse(chapter.content_blocks)
            return Array.isArray(parsed) && parsed.length > 0 ? parsed : null
        } catch { return null }
    })()

    const hasContent = blocks !== null || !!chapter.newsletter

    useEffect(() => {
        const container = proseRef.current
        if (!container || !chapter.newsletter) return

        container.querySelectorAll("pre").forEach((pre) => {
            if (pre.dataset.processed) return
            pre.dataset.processed = "true"

            const codeEl = pre.querySelector("code") as HTMLElement | null
            if (!codeEl) return

            hljs.highlightElement(codeEl)

            const rawText = codeEl.innerText
            const lineSpans = codeEl.innerHTML.split("\n")
            if (lineSpans[lineSpans.length - 1] === "") lineSpans.pop()

            codeEl.innerHTML = lineSpans
                .map((line, i) =>
                    `<span class="hljs-line" style="display:table-row">`
                    + `<span style="display:table-cell;user-select:none;padding-right:16px;min-width:2.5rem;text-align:right;color:#636d83;font-size:0.75rem;line-height:1.6">${i + 1}</span>`
                    + `<span style="display:table-cell;width:100%;line-height:1.6">${line}</span>`
                    + `</span>`
                )
                .join("\n")

            codeEl.style.display = "table"
            codeEl.style.width = "100%"

            Object.assign(pre.style, {
                position: "relative", borderRadius: "10px",
                padding: "0", overflow: "hidden", background: "transparent",
            })

            const scrollWrap = document.createElement("div")
            scrollWrap.style.cssText = "overflow-x:auto;padding:1rem 1.25rem"
            pre.insertBefore(scrollWrap, codeEl)
            scrollWrap.appendChild(codeEl)

            const ICON_COPY = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`
            const ICON_CHECK = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`

            const btn = document.createElement("button")
            btn.title = "Copy code"
            btn.innerHTML = ICON_COPY
            Object.assign(btn.style, {
                position: "absolute", top: "10px", right: "10px",
                background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: "6px", padding: "5px 8px", cursor: "pointer",
                color: "#9da5b4", display: "flex", alignItems: "center",
                justifyContent: "center", transition: "all 0.15s",
            })
            btn.addEventListener("mouseenter", () => { btn.style.background = "rgba(255,255,255,0.15)"; btn.style.color = "#fff" })
            btn.addEventListener("mouseleave", () => { btn.style.background = "rgba(255,255,255,0.08)"; btn.style.color = "#9da5b4" })
            btn.addEventListener("click", async () => {
                try {
                    await navigator.clipboard.writeText(rawText)
                    btn.innerHTML = ICON_CHECK
                    btn.style.color = "#4ade80"
                    setTimeout(() => { btn.innerHTML = ICON_COPY; btn.style.color = "#9da5b4" }, 2000)
                } catch { /* clipboard denied */ }
            })
            pre.appendChild(btn)
        })
    }, [chapter.id])

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
                            ) : chapter.newsletter ? (
                                <div
                                    ref={proseRef}
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
                                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(chapter.newsletter) }}
                                />
                            ) : null}
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
                                        chapter.newsletter ? "bg-indigo-400" : "bg-muted-foreground/30"
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
