import { useEffect, useRef, useState } from "react"
import { Sparkles, BookOpen, ChevronDown, Loader2, CheckCircle2 } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { getRequest, postRequest } from "@/services"
import useStore from "@/store"

interface Syllabus {
    skill_id: number
    email: string
    skill: string
    days: number
    hours: number
    total_tasks: number
    completed_tasks: number
}

export default function GenerateContentPage() {
    const [syllabi, setSyllabi] = useState<Syllabus[]>([])
    const [loadingList, setLoadingList] = useState(true)
    const [selectedId, setSelectedId] = useState<number | "">("")
    const [generating, setGenerating] = useState(false)
    const [done, setDone] = useState(false)
    const { setPluginName, setPluginInfo } = useStore((state: any) => state)

    useEffect(() => {
        setPluginName("Generate Content")
        setPluginInfo("Generate newsletter content for a subscriber's upcoming days.")
    }, [setPluginName, setPluginInfo])

    const fetchedRef = useRef(false)

    useEffect(() => {
        if (fetchedRef.current) return
        fetchedRef.current = true
        async function fetchSyllabi() {
            const { success, data } = await getRequest("/py/syllabi")
            if (success) setSyllabi(data)
            setLoadingList(false)
        }
        fetchSyllabi()
    }, [])

    const selected = syllabi.find((s) => s.skill_id === selectedId)
    const progress = selected && selected.total_tasks > 0
        ? Math.round((selected.completed_tasks / selected.total_tasks) * 100)
        : 0

    async function handleGenerate() {
        if (!selectedId) return
        setGenerating(true)
        setDone(false)
        const { success } = await postRequest("/py/generate-content", { skill_id: selectedId })
        setGenerating(false)
        if (success) setDone(true)
    }

    return (
        <div className="p-6 max-w-xl space-y-6">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Generate Content</h1>
                <p className="text-muted-foreground mt-1">
                    Pick a subscriber and generate newsletter content for their next 10 days.
                </p>
            </div>

            <Card>
                <CardHeader className="pb-3">
                    <p className="text-sm font-medium">Select subscriber</p>
                </CardHeader>
                <CardContent className="space-y-4">
                    {loadingList ? (
                        <Skeleton className="h-10 w-full rounded-md" />
                    ) : (
                        <div className="relative">
                            <select
                                className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2 pr-9 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                                value={selectedId}
                                onChange={(e) => {
                                    setSelectedId(e.target.value ? Number(e.target.value) : "")
                                    setDone(false)
                                }}
                            >
                                <option value="">— choose a subscriber —</option>
                                {syllabi.map((s) => (
                                    <option key={s.skill_id} value={s.skill_id}>
                                        {s.skill} · {s.email}
                                    </option>
                                ))}
                            </select>
                            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        </div>
                    )}

                    {/* preview card for selected subscriber */}
                    {selected && (
                        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                            <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                                        <BookOpen className="h-4 w-4" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-semibold">{selected.skill}</p>
                                        <p className="text-xs text-muted-foreground">{selected.email}</p>
                                    </div>
                                </div>
                                <Badge variant="outline" className="text-xs">
                                    {selected.days} days · {selected.hours}h/day
                                </Badge>
                            </div>
                            <div className="space-y-1">
                                <div className="flex justify-between text-xs text-muted-foreground">
                                    <span>Progress</span>
                                    <span>{selected.completed_tasks} / {selected.total_tasks} days done</span>
                                </div>
                                <Progress value={progress} className="h-1.5" />
                            </div>
                        </div>
                    )}

                    <Button
                        className="w-full"
                        disabled={!selectedId || generating}
                        onClick={handleGenerate}
                    >
                        {generating ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Generating…
                            </>
                        ) : done ? (
                            <>
                                <CheckCircle2 className="h-4 w-4 mr-2 text-emerald-500" />
                                Content Generated
                            </>
                        ) : (
                            <>
                                <Sparkles className="h-4 w-4 mr-2" />
                                Generate Content
                            </>
                        )}
                    </Button>

                    {done && (
                        <p className="text-center text-sm text-emerald-600">
                            Content for the next 10 days has been generated successfully.
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
