import { useEffect, useId, useRef, useState } from "react"
import mermaid from "mermaid"
import hljs from "highlight.js"
import "highlight.js/styles/atom-one-dark.css"

mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "sandbox" })

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
    const [copied, setCopied] = useState(false)

    useEffect(() => {
        if (!ref.current) return
        ref.current.textContent = code
        try {
            if (language) {
                ref.current.innerHTML = hljs.highlight(code, { language }).value
            } else {
                hljs.highlightElement(ref.current)
            }
        } catch {
            hljs.highlightElement(ref.current)
        }
        ref.current.classList.add("hljs")
    }, [code, language])

    const lines = code.split("\n")
    if (lines[lines.length - 1] === "") lines.pop()

    const ICON_COPY = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>`
    const ICON_CHECK = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`

    async function handleCopy() {
        try {
            await navigator.clipboard.writeText(code)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch { /* clipboard denied */ }
    }

    return (
        <div className="relative rounded-xl border border-white/10 bg-[#282c34] text-sm shadow-lg overflow-hidden">
            <button
                type="button"
                onClick={handleCopy}
                title="Copy code"
                aria-label={copied ? "Copied code" : "Copy code"}
                dangerouslySetInnerHTML={{ __html: copied ? ICON_CHECK : ICON_COPY }}
                style={{
                    position: "absolute", top: 10, right: 10,
                    background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6, padding: "5px 8px", cursor: "pointer",
                    color: copied ? "#4ade80" : "#9da5b4", display: "flex",
                    alignItems: "center", justifyContent: "center",
                }}
            />
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
        </div>
    )
}

/**
 * Fix common LLM Mermaid mistakes that break the parser.
 * Applied BEFORE rendering — keeps diagrams alive instead of falling back.
 */
function sanitizeDiagram(code: string): string {
    const cleanLabel = (s: string) =>
        s.replace(/\//g, " or ").replace(/:/g, " -").replace(/&/g, " and ").replace(/"/g, "")

    // Pass 1 — smart multi-line label merge.
    // Loop until node brackets are balanced, merging continuation lines one at a time.
    // A line that opens a new edge/statement (-->, ---, subgraph, end) stops the merge
    // even if brackets are still unbalanced.
    const rawLines = code.split("\n")
    const merged: string[] = []
    let i = 0
    while (i < rawLines.length) {
        let line = rawLines[i]
        i++
        while (i < rawLines.length) {
            const sq = (line.match(/\[/g)?.length ?? 0) - (line.match(/\]/g)?.length ?? 0)
            const pa = (line.match(/\(/g)?.length ?? 0) - (line.match(/\)/g)?.length ?? 0)
            const cu = (line.match(/\{/g)?.length ?? 0) - (line.match(/\}/g)?.length ?? 0)
            if (sq <= 0 && pa <= 0 && cu <= 0) break  // balanced — done
            const next = rawLines[i]
            if (next === undefined) break
            if (/-->|---|subgraph|\bend\b|^\s*(?:style|classDef|linkStyle|click)\s/.test(next)) break  // new statement — stop
            line = line.trimEnd() + " " + next.trim()
            i++
        }
        merged.push(line)
    }

    // Pass 2 — per-line fixes
    return merged
        .map(line => {
            // Close any still-unclosed brackets at end of line
            const sq = (line.match(/\[/g)?.length ?? 0) - (line.match(/\]/g)?.length ?? 0)
            if (sq > 0) line += "]".repeat(sq)
            const pa = (line.match(/\(/g)?.length ?? 0) - (line.match(/\)/g)?.length ?? 0)
            if (pa > 0) line += ")".repeat(pa)
            const cu = (line.match(/\{/g)?.length ?? 0) - (line.match(/\}/g)?.length ?? 0)
            if (cu > 0) line += "}".repeat(cu)

            // Fix edge labels placed AFTER the destination node
            // Wrong: --> C[Label] |edge text|   Right: -->|edge text| C[Label]
            line = line.replace(
                /(-->)\s*([A-Za-z][\w]*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?)\s*\|([^|\n]+)\|/g,
                (_, arr, node, edgeLabel) => `${arr}|${edgeLabel.trim()}| ${node}`,
            )

            // Fix unclosed pipe edge labels where the destination node got merged into the label.
            // e.g.: A -->|check cache miss Bfibonacci4  →  A -->|check cache miss| B[fibonacci4]
            line = line.replace(
                /(--[->])\|([^|\n]+)\s([A-Z])(\w*)\s*$/,
                (_, edge, label, nodeId, nodeLabel) => {
                    const nl = nodeLabel.trim()
                    return `${edge}|${label.trim()}| ${nodeId}${nl ? `[${nl}]` : ""}`
                },
            )
            // Fallback: strip any still-unclosed pipe edge labels so the parser doesn't choke.
            line = line.replace(/(--[->]|\.->)\|[^|\n]+$/, "$1")

            // Clean forbidden characters inside node labels and edge labels.
            // HTML-mode labels ["..."] preserve their quotes so <br/> and : remain valid;
            // only & and -- (which Mermaid misreads as an edge outside quotes) are neutralised.
            return line
                .replace(/\[([^\]]+)\]/g, (_, c) => {
                    if (c.startsWith('"') && c.length > 1) {
                        // c may be missing its closing " if the bracket closer added ] without it
                        const inner = (c.endsWith('"') ? c.slice(1, -1) : c.slice(1))
                            .replace(/&/g, " and ").replace(/--/g, "–")
                        return `["${inner}"]`
                    }
                    return `[${cleanLabel(c)}]`
                })
                .replace(/\(([^)]+)\)/g,  (_, c) => `(${cleanLabel(c)})`)
                .replace(/\{([^}]+)\}/g,  (_, c) => `{${cleanLabel(c)}}`)
                .replace(/\|([^|\n]+)\|/g, (_, c) => `|${cleanLabel(c)}|`)
        })
        .join("\n")
}

/** Strip Mermaid-only directives that add zero meaning as plain text. */
function stripDiagramMeta(code: string): string {
    return code
        .split("\n")
        .filter(line => {
            const t = line.trim().toLowerCase()
            return !t.startsWith("style ")
                && !t.startsWith("classdef ")
                && !t.startsWith("linkstyle ")
                && !t.startsWith("click ")
                && !t.startsWith("%%")
        })
        .join("\n")
        .trim()
}

export function MermaidBlock({ code }: { code: string }) {
    const id = useId()
    const ref = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!ref.current) return
        let cancelled = false
        const renderId = `mermaid-${id.replace(/[^a-zA-Z0-9]/g, "")}`

        function showFallback() {
            if (cancelled || !ref.current) return
            const pre = document.createElement("pre")
            pre.className = "text-xs text-muted-foreground whitespace-pre-wrap p-4"
            pre.textContent = stripDiagramMeta(code)
            ref.current.replaceChildren(pre)
        }

        // Parse first — if the syntax is invalid, skip render entirely so the
        // Mermaid error bomb never reaches the DOM. Only render on parse success.
        const sanitized = sanitizeDiagram(code)
        mermaid.parse(sanitized)
            .then(() => mermaid.render(renderId, sanitized))
            .then(({ svg }) => {
                if (cancelled || !ref.current) return
                ref.current.innerHTML = svg
            })
            .catch(showFallback)

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
