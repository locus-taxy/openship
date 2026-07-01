import { useState } from "react"
import { Loader2, Sparkles, Send } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { postRequest } from "@/services"

type Answer = { answer: string; citations: { title: string; page_id: string }[] }

export function KnowledgeAsk() {
    const [question, setQuestion] = useState("")
    const [loading, setLoading] = useState(false)
    const [result, setResult] = useState<Answer | null>(null)

    async function ask(e: React.FormEvent) {
        e.preventDefault()
        if (!question.trim() || loading) return
        setLoading(true)
        setResult(null)
        const { success, data } = await postRequest("/py/knowledge/query", { question: question.trim() })
        setLoading(false)
        if (success) setResult(data)
    }

    return (
        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
            <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-primary" />
                <p className="text-sm font-medium">Ask about your company docs</p>
            </div>
            <form onSubmit={ask} className="flex gap-2">
                <input
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    placeholder="e.g. How does multi-tenancy work? Where is the payments service?"
                    className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
                />
                <Button type="submit" disabled={loading || !question.trim()}>
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
            </form>

            {result && (
                <div className="space-y-3 rounded-lg bg-muted/40 p-3">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{result.answer}</p>
                    {result.citations.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
                            <span className="text-xs text-muted-foreground">Sources:</span>
                            {result.citations.map(c => (
                                <Badge key={c.page_id} variant="outline" className="text-[11px]">{c.title}</Badge>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
