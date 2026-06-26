import { useEffect, useState } from "react"
import { useNavigate } from "react-router"
import { GraduationCap, Loader2, PlayCircle, Sparkles, CheckCircle2, CircleDot, Plus, Trash2, Settings } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Dialog, DialogContent, DialogDescription, DialogFooter,
    DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { getRequest, postRequest } from "@/services"
import api from "@/services"
import useStore from "@/store"
import { LlmBar } from "@/components/llm-bar"

const ROLE_SUGGESTIONS = ["Backend Engineer", "DevOps Engineer", "SDET", "Product Manager"]

type Plan = {
    id: number
    role: string
    company: string
    status: string
    share_enabled: boolean
    total_days: number
    completed_days: number
    created_at: string
}

function PlanCard({ plan, onStart, onDelete }: { plan: Plan; onStart: (id: number) => void; onDelete: (id: number) => void }) {
    const progress = plan.total_days > 0 ? Math.round((plan.completed_days / plan.total_days) * 100) : 0
    const isCompleted = plan.completed_days === plan.total_days && plan.total_days > 0
    const isInProgress = plan.completed_days > 0 && !isCompleted

    return (
        <Card className="relative overflow-hidden border border-border/60 bg-card hover:shadow-md hover:border-border transition-all duration-200 flex flex-col group">
            <div className={cn(
                "absolute top-0 left-0 right-0 h-0.5",
                isCompleted ? "bg-gradient-to-r from-emerald-400 to-teal-500"
                    : isInProgress ? "bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500"
                    : "bg-gradient-to-r from-violet-500 via-indigo-500 to-blue-500"
            )} />

            <CardHeader className="pb-2 pt-4 px-4 sm:px-5">
                <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2.5 min-w-0">
                        <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                            isCompleted ? "bg-emerald-500/10 text-emerald-600"
                                : isInProgress ? "bg-indigo-500/10 text-indigo-600"
                                : "bg-primary/10 text-primary"
                        )}>
                            <GraduationCap className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                            <h3 className="text-sm font-semibold leading-snug">{plan.role}</h3>
                            <p className="text-xs text-muted-foreground">{plan.company}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                        <Badge variant="outline" className={cn("text-xs",
                            isCompleted ? "bg-emerald-500/10 text-emerald-600 border-emerald-200"
                                : isInProgress ? "bg-indigo-500/10 text-indigo-600 border-indigo-200"
                                : "text-muted-foreground"
                        )}>
                            {isCompleted ? "Completed" : isInProgress ? "In Progress" : "Not Started"}
                        </Badge>
                        <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); onDelete(plan.id) }}
                            className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive p-0.5 rounded"
                            title="Delete plan"
                        >
                            <Trash2 className="h-3.5 w-3.5" />
                        </button>
                    </div>
                </div>
            </CardHeader>

            <CardContent className="flex-1 flex flex-col pt-0 px-4 sm:px-5 pb-4 space-y-3">
                <div className="space-y-1.5">
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Progress</span>
                        <span className="font-medium text-foreground">{plan.completed_days} / {plan.total_days} days</span>
                    </div>
                    <Progress value={progress} className="h-1.5" />
                    <p className="text-right text-xs font-semibold text-primary">{progress}%</p>
                </div>
                <Button className="w-full" onClick={() => onStart(plan.id)}>
                    <PlayCircle className="h-4 w-4 mr-2" />
                    {isCompleted ? "Review" : isInProgress ? "Continue" : "Start"}
                </Button>
            </CardContent>
        </Card>
    )
}

function CardSkeleton() {
    return (
        <Card className="overflow-hidden border border-border/60">
            <div className="h-0.5 bg-muted" />
            <CardHeader className="pb-3 pt-4">
                <div className="flex items-start gap-2.5">
                    <Skeleton className="h-8 w-8 rounded-lg shrink-0" />
                    <div className="space-y-1.5 flex-1">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-16" />
                    </div>
                </div>
            </CardHeader>
            <CardContent className="space-y-3">
                <Skeleton className="h-1.5 w-full rounded-full" />
                <Skeleton className="h-9 w-full rounded-md" />
            </CardContent>
        </Card>
    )
}

export default function OnboardingPage() {
    const [plans, setPlans] = useState<Plan[]>([])
    const [loading, setLoading] = useState(true)
    const [showForm, setShowForm] = useState(false)
    const [role, setRole] = useState("")
    const [generating, setGenerating] = useState(false)
    const [deleteId, setDeleteId] = useState<number | null>(null)
    const [deleting, setDeleting] = useState(false)
    const navigate = useNavigate()
    const { setPluginName } = useStore((state: any) => state)

    useEffect(() => { setPluginName("Onboarding") }, [setPluginName])

    useEffect(() => {
        getRequest("/py/onboarding").then(({ success, data }) => {
            if (success) setPlans(data)
            setLoading(false)
        })
    }, [])

    async function handleGenerate(e: React.FormEvent) {
        e.preventDefault()
        if (!role.trim()) return
        setGenerating(true)
        const { success, data } = await postRequest("/py/onboarding/generate", { role: role.trim(), company: "Locus" })
        setGenerating(false)
        if (success) {
            navigate(`/onboarding/${data.plan.id}`)
        }
    }

    async function handleDeleteConfirm() {
        if (!deleteId) return
        setDeleting(true)
        try {
            await api.delete(`/py/onboarding/${deleteId}`)
            setPlans(prev => prev.filter(p => p.id !== deleteId))
        } catch { /* leave unchanged on error */ }
        finally {
            setDeleting(false)
            setDeleteId(null)
        }
    }

    const total = plans.length
    const completed = plans.filter(p => p.completed_days === p.total_days && p.total_days > 0).length
    const inProgress = plans.filter(p => p.completed_days > 0 && !(p.completed_days === p.total_days && p.total_days > 0)).length

    return (
        <div className="p-4 sm:p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">Onboarding</h1>
                    <p className="text-muted-foreground text-sm mt-0.5">Role-based onboarding plans from Locus docs</p>
                </div>
                <Button onClick={() => setShowForm(v => !v)}>
                    <Plus className="h-4 w-4 mr-2" />New Plan
                </Button>
            </div>

            {/* LLM selector */}
            <LlmBar />

            {/* Enroll form */}
            {showForm && (
                <div className="rounded-2xl border border-border bg-card shadow-sm max-w-md">
                    <form onSubmit={handleGenerate}>
                        <div className="p-5 space-y-3">
                            <Label className="text-sm font-medium">Your Role</Label>
                            <Input placeholder="e.g. Backend Engineer" value={role} onChange={e => setRole(e.target.value)} className="rounded-xl" autoFocus />
                            <div className="flex flex-wrap gap-1.5">
                                {ROLE_SUGGESTIONS.map(r => (
                                    <button key={r} type="button" onClick={() => setRole(r)}
                                        className={cn("text-xs px-2.5 py-1 rounded-full border transition-all",
                                            role === r ? "border-primary bg-primary/10 text-primary font-medium" : "border-border text-muted-foreground hover:border-primary/60 hover:text-foreground"
                                        )}>
                                        {r}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="border-t border-border px-5 py-3 bg-muted/30 rounded-b-2xl flex gap-2">
                            <Button type="submit" className="flex-1 rounded-xl" disabled={generating || !role.trim()}>
                                {generating ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Generating…</> : <><Sparkles className="h-4 w-4 mr-2" />Generate Plan</>}
                            </Button>
                            <Button type="button" variant="outline" className="rounded-xl" onClick={() => setShowForm(false)}>Cancel</Button>
                        </div>
                    </form>
                </div>
            )}

            {/* Stats */}
            {!loading && total > 0 && (
                <div className="grid grid-cols-3 gap-3">
                    {[
                        { icon: GraduationCap, label: "Total", value: total, color: "bg-primary/10 text-primary" },
                        { icon: CircleDot, label: "In progress", value: inProgress, color: "bg-indigo-500/10 text-indigo-600" },
                        { icon: CheckCircle2, label: "Completed", value: completed, color: "bg-emerald-500/10 text-emerald-600" },
                    ].map(({ icon: Icon, label, value, color }) => (
                        <div key={label} className="flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3">
                            <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg", color)}>
                                <Icon className="h-4 w-4" />
                            </div>
                            <div>
                                <p className="text-xl font-bold leading-none">{value}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Plan grid */}
            {loading ? (
                <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
                    {[...Array(3)].map((_, i) => <CardSkeleton key={i} />)}
                </div>
            ) : plans.length === 0 ? (
                <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
                    <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted mb-4">
                        <GraduationCap className="h-7 w-7 text-muted-foreground" />
                    </div>
                    <h3 className="font-semibold text-lg">No onboarding plans yet</h3>
                    <p className="text-muted-foreground text-sm mt-1 mb-5 max-w-xs">Generate a personalised plan based on your role and Locus docs.</p>
                    <Button onClick={() => setShowForm(true)}><Plus className="h-4 w-4 mr-2" />New Plan</Button>
                </Card>
            ) : (
                <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
                    {plans.map(plan => (
                        <PlanCard
                            key={plan.id}
                            plan={plan}
                            onStart={id => navigate(`/onboarding/${id}`)}
                            onDelete={id => setDeleteId(id)}
                        />
                    ))}
                </div>
            )}

            <Dialog open={deleteId !== null} onOpenChange={open => { if (!open) setDeleteId(null) }}>
                <DialogContent className="max-w-sm">
                    <DialogHeader>
                        <DialogTitle>Delete onboarding plan?</DialogTitle>
                        <DialogDescription>
                            This will permanently delete the plan and all generated day content. This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="gap-2">
                        <Button variant="outline" disabled={deleting} onClick={() => setDeleteId(null)}>Cancel</Button>
                        <Button
                            variant="destructive"
                            onClick={handleDeleteConfirm}
                            disabled={deleting}
                        >
                            {deleting ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Deleting…</> : "Delete"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
