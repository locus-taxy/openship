import { useEffect, useRef, useState } from "react"
import { Sparkles, BookOpen, ChevronDown, Loader2, CheckCircle2, CalendarDays, Clock } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { getRequest, postRequest } from "@/services"
import useStore from "@/store"

interface Enrollee {
    skill_id: number
    email: string
    skill: string
    days: number
    hours: number
    total_tasks: number
}

export default function GenerateSyllabusPage() {
    const [enrollees, setEnrollees] = useState<Enrollee[]>([])
    const [loadingList, setLoadingList] = useState(true)
    const [selectedId, setSelectedId] = useState<number | "">("")
    const [generating, setGenerating] = useState(false)
    const [done, setDone] = useState(false)
    const { setPluginName } = useStore((state: any) => state)

    useEffect(() => {
        setPluginName("Generate Syllabus")
    }, [setPluginName])

    const fetchedRef = useRef(false)

    useEffect(() => {
        if (fetchedRef.current) return
        fetchedRef.current = true
        async function fetchEnrollees() {
            const { success, data } = await getRequest("/py/syllabi")
            if (success) setEnrollees(data)
            setLoadingList(false)
        }
        fetchEnrollees()
    }, [])

    const selected = enrollees.find((s) => s.skill_id === selectedId)
    const alreadyHasSyllabus = (selected?.total_tasks ?? 0) > 0

    async function handleGenerate() {
        if (!selected) return
        setGenerating(true)
        setDone(false)
        const { success } = await postRequest("/py/generate-syllabus", {
            skill: selected.skill,
        })
        setGenerating(false)
        if (success) setDone(true)
    }

    return (
        <div className="p-6 max-w-xl space-y-6">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Generate Syllabus</h1>
                <p className="text-muted-foreground mt-1">
                    Pick an enrollee and generate their Month → Week → Day learning plan.
                </p>
            </div>

            <Card>
                <CardHeader className="pb-3">
                    <p className="text-sm font-medium">Select enrollee</p>
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
                                <option value="">— choose an enrollee —</option>
                                {enrollees.map((s) => (
                                    <option key={s.skill_id} value={s.skill_id}>
                                        {s.skill} · {s.email}
                                    </option>
                                ))}
                            </select>
                            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        </div>
                    )}

                    {selected && (
                        <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3">
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex items-center gap-2">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                                        <BookOpen className="h-4 w-4" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-semibold">{selected.skill}</p>
                                        <p className="text-xs text-muted-foreground">{selected.email}</p>
                                    </div>
                                </div>
                                {alreadyHasSyllabus ? (
                                    <Badge className="bg-amber-500/15 text-amber-600 border-amber-300 hover:bg-amber-500/20 text-xs">
                                        Syllabus exists
                                    </Badge>
                                ) : (
                                    <Badge variant="outline" className="text-xs text-muted-foreground">
                                        No syllabus yet
                                    </Badge>
                                )}
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div className="flex items-center gap-2 rounded-md bg-background px-3 py-2">
                                    <CalendarDays className="h-4 w-4 text-muted-foreground" />
                                    <div>
                                        <p className="text-xs text-muted-foreground">Duration</p>
                                        <p className="text-sm font-medium">{selected.days} days</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 rounded-md bg-background px-3 py-2">
                                    <Clock className="h-4 w-4 text-muted-foreground" />
                                    <div>
                                        <p className="text-xs text-muted-foreground">Daily</p>
                                        <p className="text-sm font-medium">{selected.hours} hr{selected.hours !== 1 ? "s" : ""}</p>
                                    </div>
                                </div>
                            </div>
                            {alreadyHasSyllabus && (
                                <p className="text-xs text-amber-600 bg-amber-50 dark:bg-amber-950/30 rounded-md px-3 py-2">
                                    This enrollee already has {selected.total_tasks} days planned. Generating again will add duplicate tasks.
                                </p>
                            )}
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
                                Syllabus Generated
                            </>
                        ) : (
                            <>
                                <Sparkles className="h-4 w-4 mr-2" />
                                Generate Syllabus
                            </>
                        )}
                    </Button>

                    {done && (
                        <p className="text-center text-sm text-emerald-600">
                            Syllabus generated successfully. You can now generate content for this enrollee.
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
