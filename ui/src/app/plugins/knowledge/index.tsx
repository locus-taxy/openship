import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router"
import { Plus, Send, Loader2, Trash2, Sparkles, ArrowLeft, PanelLeft, BookOpen, FileText, ListChecks, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { getRequest, postRequest } from "@/services"
import api from "@/services"
import useStore from "@/store"
import { useSidebar } from "@/components/ui/sidebar"
import { BlockRenderer, type ContentBlock } from "@/app/plugins/syllabi/block-renderer"
import { LlmBar } from "@/components/llm-bar"

type Citation = { title: string; page_id: string; source?: "confluence" | "jira"; url?: string | null }
type Msg = {
    id?: number
    role: "user" | "assistant"
    content: string
    blocks?: ContentBlock[] | null
    citations?: Citation[]
    pending?: boolean
}
type Chat = { id: number; title: string; updated_at?: string | null }
type Status = { connected: boolean; chunk_count: number }

const EXAMPLES = [
    "How does multi-tenancy work?",
    "Where is the payments service?",
    "What is our deployment process?",
    "How do I set up the project locally?",
]

export default function KnowledgePage() {
    const { setPluginName, setHideHeader } = useStore((s: any) => s)
    const { setOpen } = useSidebar()
    const navigate = useNavigate()

    const [status, setStatus] = useState<Status | null>(null)
    const [loading, setLoading] = useState(true)
    const [chats, setChats] = useState<Chat[]>([])
    const [activeId, setActiveId] = useState<number | null>(null)
    const [messages, setMessages] = useState<Msg[]>([])
    const [input, setInput] = useState("")
    const [sending, setSending] = useState(false)
    const [navOpen, setNavOpen] = useState(false)
    const scrollRef = useRef<HTMLDivElement>(null)
    // Which chat is currently in view — read synchronously in async handlers so a
    // response that lands after the user switched chats doesn't touch the wrong thread.
    const activeIdRef = useRef<number | null>(null)

    // Collapse the app chrome for a focused, full-screen chat surface.
    useEffect(() => {
        setPluginName("Knowledge")
        setHideHeader(true)
        setOpen(false)
        return () => { setHideHeader(false); setOpen(true) }
    }, [])

    useEffect(() => {
        getRequest("/py/confluence/status").then(({ success, data }) => {
            if (success) setStatus(data)
            setLoading(false)
        })
        loadChats()
    }, [])

    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
    }, [messages])

    async function loadChats() {
        const { success, data } = await getRequest("/py/knowledge/chats")
        if (success) setChats(data)
    }

    async function openChat(id: number) {
        setActiveId(id)
        activeIdRef.current = id
        setNavOpen(false)
        setInput("")
        setMessages([])
        const { success, data } = await getRequest(`/py/knowledge/chats/${id}`)
        // Ignore a late response if the user has since switched to another chat.
        if (success && activeIdRef.current === id) setMessages(data.messages)
    }

    function newChat() {
        setActiveId(null)
        activeIdRef.current = null
        setMessages([])
        setInput("")
        setNavOpen(false)
    }

    async function deleteChat(id: number) {
        try { await api.delete(`/py/knowledge/chats/${id}`) } catch { return }
        setChats(prev => prev.filter(c => c.id !== id))
        if (activeId === id) newChat()
    }

    async function send(text: string) {
        const q = text.trim()
        if (!q || sending) return

        let chatId = activeId
        if (chatId == null) {
            const { success, data } = await postRequest("/py/knowledge/chats", {})
            if (!success) return
            chatId = data.id
            setActiveId(chatId)
            activeIdRef.current = chatId
            setChats(prev => [data, ...prev])
        }

        setInput("")
        setMessages(prev => [...prev, { role: "user", content: q }, { role: "assistant", content: "", pending: true }])
        setSending(true)
        const { success, data } = await postRequest(`/py/knowledge/chats/${chatId}/messages`, { question: q })
        setSending(false)
        // If the user switched to a different chat mid-send, don't mutate the now-visible
        // thread; the sent chat will show the persisted turns when reopened.
        if (activeIdRef.current !== chatId) { loadChats(); return }
        if (success) {
            setMessages(prev => [...prev.slice(0, -1), data.assistant])
            loadChats()  // refresh title + ordering
        } else {
            setMessages(prev => prev.slice(0, -1))  // drop the pending assistant; toast already shown
        }
    }

    if (loading) {
        return (
            <div className="flex h-[100dvh] items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
        )
    }

    const ready = !!status?.connected && status.chunk_count > 0
    if (!ready) {
        return (
            <div className="flex h-[100dvh] flex-col items-center justify-center gap-4 p-6 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
                    <Sparkles className="h-7 w-7 text-muted-foreground" />
                </div>
                <div>
                    <h3 className="font-semibold text-lg">Your knowledge base isn't ready yet</h3>
                    <p className="text-muted-foreground text-sm mt-1 max-w-sm">
                        Connect Atlassian and ingest your Confluence &amp; Jira content from Connections, then come back to chat with it.
                    </p>
                </div>
                <Button onClick={() => navigate("/connections")}>
                    <BookOpen className="h-4 w-4 mr-2" />Go to Connections
                </Button>
            </div>
        )
    }

    return (
        <div className="flex overflow-hidden bg-background" style={{ height: "100dvh" }}>
            {/* Mobile overlay */}
            {navOpen && <div className="fixed inset-0 z-40 bg-black/50 sm:hidden" onClick={() => setNavOpen(false)} />}

            {/* History sidebar */}
            <aside className={cn(
                "z-50 flex w-72 shrink-0 flex-col border-r border-border bg-card",
                "fixed inset-y-0 left-0 transition-transform sm:static sm:translate-x-0",
                navOpen ? "translate-x-0" : "-translate-x-full",
            )}>
                {/* Brand */}
                <div className="flex items-center gap-2.5 border-b border-border px-4 py-3.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600">
                        <Sparkles className="h-4 w-4 text-white" />
                    </div>
                    <span className="bg-gradient-to-r from-violet-500 to-indigo-500 bg-clip-text text-lg font-bold text-transparent">
                        Openship
                    </span>
                </div>

                <div className="p-3">
                    <Button className="w-full justify-start gap-2" variant="outline" onClick={newChat}>
                        <Plus className="h-4 w-4" />New chat
                    </Button>
                </div>

                <div className="px-4 pb-1.5 pt-1">
                    <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/60">Chats</p>
                </div>
                <div className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
                    {chats.length === 0 ? (
                        <p className="px-2 py-6 text-center text-xs text-muted-foreground">No chats yet — start one above.</p>
                    ) : chats.map(c => (
                        <div
                            key={c.id}
                            className={cn(
                                "group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-sm transition-colors",
                                activeId === c.id ? "bg-muted font-medium" : "hover:bg-muted/60",
                            )}
                            onClick={() => openChat(c.id)}
                        >
                            <span className="flex-1 truncate">{c.title || "New chat"}</span>
                            <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); deleteChat(c.id) }}
                                className="opacity-0 transition-opacity group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                                title="Delete chat"
                            >
                                <Trash2 className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    ))}
                </div>
            </aside>

            {/* Chat panel */}
            <div className="flex flex-1 flex-col min-w-0">
                <header className="flex items-center gap-3 border-b border-border px-4 py-3">
                    <Button variant="outline" size="sm" className="h-9 gap-1.5" onClick={() => navigate(-1)}>
                        <ArrowLeft className="h-4 w-4" /><span className="hidden sm:inline">Back</span>
                    </Button>
                    <Button variant="ghost" size="icon" className="h-9 w-9 sm:hidden" onClick={() => setNavOpen(true)}>
                        <PanelLeft className="h-4 w-4" />
                    </Button>
                    <div className="flex min-w-0 items-center gap-2">
                        <Sparkles className="h-4 w-4 shrink-0 text-primary" />
                        <h1 className="truncate text-sm font-semibold">Ask about your company docs</h1>
                    </div>
                    <div className="ml-auto shrink-0">
                        <LlmBar />
                    </div>
                </header>

                <div ref={scrollRef} className="flex-1 overflow-y-auto">
                    {messages.length === 0 ? (
                        <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center gap-5 p-6 text-center">
                            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                                <Sparkles className="h-6 w-6" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold">Ask anything about your docs</h2>
                                <p className="text-sm text-muted-foreground mt-1">Grounded in your indexed Confluence. Try:</p>
                            </div>
                            <div className="flex flex-wrap justify-center gap-2">
                                {EXAMPLES.map(q => (
                                    <button
                                        key={q}
                                        onClick={() => send(q)}
                                        className="rounded-full border border-border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary/60 hover:text-foreground"
                                    >
                                        {q}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ) : (
                        <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-6">
                            {messages.map((m, i) => {
                                if (m.role === "user") {
                                    return (
                                        <div key={m.id ?? i} className="flex justify-end">
                                            <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground">
                                                {m.content}
                                            </div>
                                        </div>
                                    )
                                }
                                // assistant
                                return (
                                    <div key={m.id ?? i} className="flex items-start gap-2.5">
                                        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                                            <Sparkles className="h-3.5 w-3.5" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            {m.pending ? (
                                                <div className="flex items-center gap-2 py-1.5 text-sm text-muted-foreground">
                                                    <Loader2 className="h-4 w-4 animate-spin" />Thinking…
                                                </div>
                                            ) : (
                                                <div className="rounded-2xl border border-border/60 bg-card px-4 py-3">
                                                    {m.blocks && m.blocks.length > 0 ? (
                                                        <BlockRenderer blocks={m.blocks} />
                                                    ) : (
                                                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</p>
                                                    )}
                                                    {m.citations && m.citations.length > 0 && (
                                                        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border/60 pt-2.5">
                                                            <span className="text-[11px] text-muted-foreground">Sources:</span>
                                                            {m.citations.map(c => <CitationChip key={`${c.source}:${c.page_id}`} c={c} />)}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>

                <form
                    onSubmit={e => { e.preventDefault(); send(input) }}
                    className="border-t border-border px-4 py-4"
                >
                    <div className="mx-auto flex max-w-3xl items-end gap-2">
                        <textarea
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input) } }}
                            rows={1}
                            placeholder="Ask about your company docs…"
                            className="max-h-40 flex-1 resize-none rounded-xl border border-border bg-background px-4 py-3 text-sm outline-none focus:border-primary"
                        />
                        <Button type="submit" size="icon" className="h-11 w-11 shrink-0 rounded-xl" disabled={sending || !input.trim()}>
                            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                        </Button>
                    </div>
                    <p className="mx-auto mt-2 max-w-3xl px-1 text-[11px] text-muted-foreground">
                        Answers are grounded in your indexed Confluence &amp; Jira. Press Enter to send, Shift+Enter for a new line.
                    </p>
                </form>
            </div>
        </div>
    )
}

// A source chip for one citation — Jira issue or Confluence page, deep-linked when
// the backend supplied a URL.
function CitationChip({ c }: { c: Citation }) {
    const isJira = c.source === "jira"
    const Icon = isJira ? ListChecks : FileText
    const label = isJira ? `${c.page_id} · ${c.title}` : c.title
    const inner = (
        <Badge
            variant="outline"
            className={cn(
                "max-w-[16rem] gap-1 truncate text-[11px]",
                isJira ? "border-indigo-200 text-indigo-700" : "border-sky-200 text-sky-700",
                c.url && "hover:bg-muted",
            )}
            title={label}
        >
            <Icon className="h-3 w-3 shrink-0" />
            <span className="truncate">{label}</span>
            {c.url && <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />}
        </Badge>
    )
    if (!c.url) return inner
    return (
        <a href={c.url} target="_blank" rel="noreferrer" className="min-w-0">
            {inner}
        </a>
    )
}
