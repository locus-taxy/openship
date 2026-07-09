import { useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { Plug, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { getRequest } from "@/services"

type Source = "confluence" | "jira"
type SourceCounts = { page_count: number; chunk_count: number }
type Status = {
    connected: boolean
    status: string | null
    sources: Record<Source, SourceCounts>
}

const NAME: Record<Source, string> = { confluence: "Confluence", jira: "Jira" }

/**
 * Compact readiness banner for a feature that depends on the knowledge base.
 * Shows nothing once the given `source` has indexed content; otherwise nudges
 * the user to the Connections page. Connecting/ingesting lives there now.
 */
export function KnowledgeBaseBanner({ source = "confluence" }: { source?: Source }) {
    const [status, setStatus] = useState<Status | null>(null)
    const [loaded, setLoaded] = useState(false)
    const navigate = useNavigate()

    useEffect(() => {
        getRequest("/py/connections/status").then(({ success, data }) => {
            if (success) setStatus(data)
            setLoaded(true)
        })
    }, [])

    if (!loaded) return null

    const ready = !!status?.connected && (status.sources?.[source]?.chunk_count ?? 0) > 0
    if (ready) return null

    const notConnected = !status?.connected
    return (
        <div className={cn(
            "flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3",
            "border-amber-200 bg-amber-50/50",
        )}>
            <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700">
                    {notConnected ? <Plug className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                </div>
                <div className="min-w-0">
                    <p className="text-sm font-medium leading-tight">
                        {notConnected
                            ? "Connect your knowledge base"
                            : `No ${NAME[source]} content indexed yet`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                        {notConnected
                            ? `Connect Atlassian and ingest ${NAME[source]} to power this feature.`
                            : `Ingest your ${NAME[source]} content to enable onboarding and answers.`}
                    </p>
                </div>
            </div>
            <Button size="sm" variant="outline" onClick={() => navigate("/connections")}>
                <Plug className="mr-2 h-4 w-4" />Go to Connections
            </Button>
        </div>
    )
}
