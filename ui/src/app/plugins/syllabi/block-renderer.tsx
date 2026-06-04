import { useEffect, useId, useRef, useState } from "react"
import mermaid from "mermaid"
import hljs from "highlight.js"
import "highlight.js/styles/atom-one-dark.css"
import { Loader2, Pencil, Play, X } from "lucide-react"
import { isRunnable, executeCode } from "@/services/executor"

mermaid.initialize({ startOnLoad: false, theme: "dark", suppressErrors: true })

export type BlockType =
    | "heading" | "paragraph" | "code"
    | "bullet_list" | "numbered_list"
    | "table" | "note" | "quote" | "divider"
    | "diagram"

export interface ContentBlock {
    type: BlockType
    content?: string
    level?: number
    language?: string
    items?: string[]
    headers?: string[]
    rows?: string[][]
    format?: string
}

export function InlineText({ text }: { text: string }) {
    const parts = text.split(/(`[^`]+`)/g)
    return (
        <>
            {parts.map((part, i) => {
                if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
                    return (
                        <code key={i} className="bg-zinc-100 text-zinc-800 px-1.5 py-0.5 rounded text-[0.82em] font-mono">
                            {part.slice(1, -1)}
                        </code>
                    )
                }
                const boldParts = part.split(/(\*\*[^*]+\*\*)/g)
                if (boldParts.length > 1) {
                    return boldParts.map((bp, j) =>
                        bp.startsWith("**") && bp.endsWith("**") && bp.length > 4
                            ? <strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>
                            : <span key={`${i}-${j}`}>{bp}</span>
                    )
                }
                return <span key={i}>{part}</span>
            })}
        </>
    )
}

export function CodeBlock({ code, language }: { code: string; language: string }) {
    const ref = useRef<HTMLElement>(null)
    const [copied, setCopied]         = useState(false)
    const [isEditing, setIsEditing]   = useState(false)
    const [editedCode, setEditedCode] = useState(code)
    const [output, setOutput]         = useState<{ stdout: string; stderr: string } | null>(null)
    const [isRunning, setIsRunning]   = useState(false)
    const [runLabel, setRunLabel]     = useState("Running…")
    const [runError, setRunError]     = useState<string | null>(null)

    useEffect(() => {
        if (!ref.current || isEditing) return
        ref.current.textContent = editedCode
        try {
            if (language) {
                ref.current.innerHTML = hljs.highlight(editedCode, { language }).value
            } else {
                hljs.highlightElement(ref.current)
            }
        } catch {
            hljs.highlightElement(ref.current)
        }
        ref.current.classList.add("hljs")
    }, [editedCode, language, isEditing])

    const lines = editedCode.split("\n")
    if (lines[lines.length - 1] === "") lines.pop()

    const ICON_COPY = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`
    const ICON_CHECK = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`

    async function handleCopy() {
        try {
            await navigator.clipboard.writeText(editedCode)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch { /* clipboard denied */ }
    }

    async function handleRun() {
        setIsRunning(true)
        setOutput(null)
        setRunError(null)
        setRunLabel(language?.toLowerCase() === "python" ? "Loading Python…" : "Running…")
        try {
            const result = await executeCode(language, editedCode)
            setOutput(result)
        } catch (e) {
            setRunError(e instanceof Error ? e.message : "Execution failed")
        } finally {
            setIsRunning(false)
        }
    }

    return (
        <div className="rounded-xl border border-white/10 bg-[#282c34] text-sm shadow-lg overflow-hidden">

            {/* Toolbar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end",
                          gap: 6, padding: "8px 10px 0" }}>

                {/* Edit / Done toggle */}
                <button
                    type="button"
                    onClick={() => {
                        if (isEditing) { setOutput(null); setRunError(null) }
                        setIsEditing(e => !e)
                    }}
                    title={isEditing ? "Done editing" : "Edit code"}
                    style={{
                        background: isEditing ? "rgba(99,211,130,0.15)" : "rgba(255,255,255,0.08)",
                        border: `1px solid ${isEditing ? "rgba(99,211,130,0.4)" : "rgba(255,255,255,0.12)"}`,
                        borderRadius: 6, padding: "4px 8px", cursor: "pointer",
                        color: isEditing ? "#4ade80" : "#9da5b4",
                        display: "flex", alignItems: "center", gap: 4, fontSize: 11,
                    }}
                >
                    {isEditing ? <><X size={11} /> Done</> : <><Pencil size={11} /> Edit</>}
                </button>

                {/* Run button — only for python and javascript */}
                {isRunnable(language) && (
                    <button
                        type="button"
                        onClick={handleRun}
                        disabled={isRunning}
                        title="Run code"
                        style={{
                            background: "rgba(99,211,130,0.15)",
                            border: "1px solid rgba(99,211,130,0.35)",
                            borderRadius: 6, padding: "4px 10px",
                            cursor: isRunning ? "default" : "pointer",
                            color: "#4ade80", display: "flex", alignItems: "center",
                            gap: 4, fontSize: 11, opacity: isRunning ? 0.6 : 1,
                        }}
                    >
                        {isRunning
                            ? <><Loader2 size={11} className="animate-spin" /> {runLabel}</>
                            : <><Play size={11} /> Run</>}
                    </button>
                )}

                {/* Copy button */}
                <button
                    type="button"
                    onClick={handleCopy}
                    title="Copy code"
                    aria-label={copied ? "Copied code" : "Copy code"}
                    dangerouslySetInnerHTML={{ __html: copied ? ICON_CHECK : ICON_COPY }}
                    style={{
                        background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: 6, padding: "5px 8px", cursor: "pointer",
                        color: copied ? "#4ade80" : "#9da5b4",
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}
                />
            </div>

            {/* Code area */}
            {isEditing ? (
                <textarea
                    value={editedCode}
                    onChange={e => setEditedCode(e.target.value)}
                    spellCheck={false}
                    style={{
                        width: "100%", boxSizing: "border-box",
                        background: "transparent", color: "#abb2bf",
                        fontFamily: "monospace", fontSize: 12, lineHeight: 1.6,
                        padding: "12px 20px", border: "none", outline: "none",
                        resize: "vertical",
                        minHeight: `${Math.max(lines.length, 4) * 1.6 * 12 + 24}px`,
                    }}
                />
            ) : (
                <div className="flex overflow-x-auto">
                    <div className="flex flex-col shrink-0 select-none text-right px-3 py-4
                                    text-[#636d83] text-xs leading-[1.6]
                                    border-r border-white/[0.08] min-w-[2.5rem]">
                        {lines.map((_, i) => <span key={i}>{i + 1}</span>)}
                    </div>
                    <div className="flex-1 overflow-x-auto px-5 py-4 min-w-0">
                        <code ref={ref} className="font-mono text-xs leading-[1.6] whitespace-pre block" />
                    </div>
                </div>
            )}

            {/* Output panel */}
            {(output !== null || runError !== null) && (
                <div style={{
                    borderTop: "1px solid rgba(255,255,255,0.08)",
                    background: "#1e2227", padding: "10px 16px",
                    maxHeight: 200, overflowY: "auto",
                }}>
                    {runError ? (
                        <>
                            <div style={{ fontSize: 10, color: "#f87171", marginBottom: 4,
                                          fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                                Error
                            </div>
                            <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 12,
                                          lineHeight: 1.6, color: "#f87171", whiteSpace: "pre-wrap" }}>
                                {runError}
                            </pre>
                        </>
                    ) : (
                        <>
                            {output!.stdout && (
                                <>
                                    <div style={{ fontSize: 10, color: "#4ade80", marginBottom: 4,
                                                  fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                                        Output
                                    </div>
                                    <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 12,
                                                  lineHeight: 1.6, color: "#abb2bf", whiteSpace: "pre-wrap" }}>
                                        {output!.stdout}
                                    </pre>
                                </>
                            )}
                            {output!.stderr && (
                                <>
                                    <div style={{ fontSize: 10, color: "#fbbf24",
                                                  marginTop: output!.stdout ? 8 : 0, marginBottom: 4,
                                                  fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                                        Stderr
                                    </div>
                                    <pre style={{ margin: 0, fontFamily: "monospace", fontSize: 12,
                                                  lineHeight: 1.6, color: "#fbbf24", whiteSpace: "pre-wrap" }}>
                                        {output!.stderr}
                                    </pre>
                                </>
                            )}
                            {!output!.stdout && !output!.stderr && (
                                <div style={{ fontSize: 12, color: "#636d83", fontStyle: "italic" }}>
                                    (no output)
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}

export function MermaidBlock({ code }: { code: string }) {
    const id = useId()
    const ref = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!ref.current) return
        let cancelled = false
        const renderId = `mermaid-${id.replace(/[^a-zA-Z0-9]/g, "")}`

        mermaid.render(renderId, code)
            .then(({ svg }) => {
                if (!cancelled && ref.current) ref.current.innerHTML = svg
            })
            .catch(() => {
                if (!cancelled && ref.current) {
                    const pre = document.createElement("pre")
                    pre.className = "text-xs text-muted-foreground whitespace-pre-wrap p-4"
                    pre.textContent = code
                    ref.current.replaceChildren(pre)
                }
            })

        return () => { cancelled = true }
    }, [code, id])

    return <div ref={ref} className="rounded-xl border border-border bg-muted/30 p-4 overflow-x-auto" />
}

export function BlockItem({ block }: { block: ContentBlock }) {
    switch (block.type) {
        case "heading": {
            const text = block.content ?? ""
            if (block.level === 1) return <h1 className="text-2xl font-bold tracking-tight text-foreground mt-6 mb-3"><InlineText text={text} /></h1>
            if (block.level === 3) return <h3 className="text-base font-semibold text-foreground mt-4 mb-1.5"><InlineText text={text} /></h3>
            return <h2 className="text-xl font-semibold text-foreground mt-5 mb-2 border-b border-border/50 pb-2"><InlineText text={text} /></h2>
        }
        case "paragraph":
            return <p className="text-zinc-600 leading-7"><InlineText text={block.content ?? ""} /></p>
        case "code":
            return <CodeBlock code={block.content ?? ""} language={block.language ?? ""} />
        case "bullet_list":
            return <ul className="list-disc pl-5 space-y-1 text-zinc-600">{block.items?.map((item, i) => <li key={i} className="leading-7"><InlineText text={item} /></li>)}</ul>
        case "numbered_list":
            return <ol className="list-decimal pl-5 space-y-1 text-zinc-600">{block.items?.map((item, i) => <li key={i} className="leading-7"><InlineText text={item} /></li>)}</ol>
        case "table":
            return (
                <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full border-collapse text-sm">
                        <thead className="bg-muted/50">
                            <tr>{block.headers?.map((h, i) => <th key={i} className="border border-border px-4 py-2.5 text-left font-semibold text-foreground"><InlineText text={h} /></th>)}</tr>
                        </thead>
                        <tbody>
                            {block.rows?.map((row, i) => (
                                <tr key={i} className={i % 2 === 1 ? "bg-muted/20" : ""}>
                                    {row.map((cell, j) => <td key={j} className="border border-border px-4 py-2 text-zinc-600"><InlineText text={cell} /></td>)}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )
        case "note":
            return (
                <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3">
                    <p className="text-sm text-foreground/80 leading-7"><InlineText text={block.content ?? ""} /></p>
                </div>
            )
        case "quote":
            return <blockquote className="border-l-4 border-primary/40 bg-muted/30 rounded-r-lg py-2 px-4 text-zinc-600 italic"><InlineText text={block.content ?? ""} /></blockquote>
        case "divider":
            return <hr className="border-border my-2" />
        case "diagram":
            return <MermaidBlock code={block.content ?? ""} />
        default:
            return null
    }
}

export function BlockRenderer({ blocks }: { blocks: ContentBlock[] }) {
    return (
        <div className="space-y-4">
            {blocks.map((block, i) => <BlockItem key={i} block={block} />)}
        </div>
    )
}
