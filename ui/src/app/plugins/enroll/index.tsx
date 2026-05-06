import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { UserPlus, ChevronDown, Loader2, Search, PenLine, Clock, CalendarDays, KeyRound, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { postRequest, getRequest } from "@/services";
import useStore from "@/store";

const SUBJECTS = [
    { group: "Programming Languages", items: ["Python", "JavaScript", "TypeScript", "Go (Golang)", "Rust", "Java", "C++", "Swift", "Kotlin", "PHP", "Ruby"] },
    { group: "Web Development", items: ["React", "Next.js", "Node.js", "FastAPI", "Django", "Express.js", "Vue.js", "Angular", "Tailwind CSS", "GraphQL"] },
    { group: "Data & AI", items: ["Machine Learning", "Deep Learning", "Data Science with Python", "Natural Language Processing", "Computer Vision", "Statistics & Probability", "Linear Algebra for ML"] },
    { group: "Cloud & DevOps", items: ["AWS Cloud", "Google Cloud Platform", "Docker & Kubernetes", "DevOps & CI/CD", "Linux System Administration"] },
    { group: "Databases", items: ["SQL & PostgreSQL", "MongoDB", "Redis", "Database Design"] },
    { group: "CS Fundamentals", items: ["Data Structures & Algorithms", "System Design", "Object-Oriented Programming", "Functional Programming", "Git & Version Control"] },
    { group: "Mobile Development", items: ["React Native", "Flutter", "iOS Development (Swift)", "Android Development (Kotlin)"] },
    { group: "Other", items: ["Cybersecurity Fundamentals", "Blockchain Development", "Prompt Engineering", "API Design & REST"] },
];

const DAY_OPTIONS = [
    { value: 30, label: "30 days" },
    { value: 60, label: "60 days" },
    { value: 90, label: "90 days" },
];

const HOUR_OPTIONS = [
    { value: 1, label: "1 hr" },
    { value: 2, label: "2 hrs" },
    { value: 3, label: "3 hrs" },
    { value: 4, label: "4 hrs" },
];

const QUICK_PICKS = ["Python", "React", "TypeScript", "Machine Learning", "System Design", "Docker & Kubernetes"];

const DIFFICULTY_OPTIONS = [
    { value: "beginner", label: "Beginner", desc: "New to this topic" },
    { value: "intermediate", label: "Intermediate", desc: "Some experience" },
    { value: "advanced", label: "Advanced", desc: "Deep expertise" },
] as const;

type Difficulty = "beginner" | "intermediate" | "advanced";

const ALL_ITEMS = ([] as string[]).concat(...SUBJECTS.map((g) => g.items));

export default function EnrollPage() {
    const navigate = useNavigate();
    const [subject, setSubject] = useState("");
    const [customSubject, setCustomSubject] = useState("");
    const [search, setSearch] = useState("");
    const [open, setOpen] = useState(false);
    const [isOther, setIsOther] = useState(false);
    const [days, setDays] = useState(90);
    const [hours, setHours] = useState(1);
    const [difficulty, setDifficulty] = useState<Difficulty>("beginner");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [hasApiKey, setHasApiKey] = useState<boolean | null>(null);
    const { setPluginName, setSettingsOpen, settingsOpen } = useStore((state: any) => state);
    const dropdownRef = useRef<HTMLDivElement>(null);

    const finalSubject = isOther ? customSubject.trim() : subject;

    const filtered = search.trim()
        ? ALL_ITEMS.filter((item) => item.toLowerCase().includes(search.toLowerCase()))
        : ALL_ITEMS;

    const noResults = search.trim() !== "" && filtered.length === 0;

    useEffect(() => {
        setPluginName("Enroll");
    }, [setPluginName]);

    useEffect(() => {
        if (settingsOpen) return; // only re-check when dialog closes (or on first load)
        async function checkApiKey() {
            const { success, data } = await getRequest("/py/auth/me/settings");
            if (success) {
                const anyKey = Object.values(data.provider_keys as Record<string, boolean>).some(Boolean);
                setHasApiKey(anyKey);
            } else {
                setHasApiKey(false);
            }
        }
        checkApiKey();
    }, [settingsOpen]);

    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    function selectSubject(item: string) {
        setSubject(item);
        setIsOther(false);
        setSearch("");
        setOpen(false);
        setError("");
    }

    function selectOther(prefill?: string) {
        setSubject("Other");
        setIsOther(true);
        if (prefill) setCustomSubject(prefill);
        setSearch("");
        setOpen(false);
        setError("");
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (hasApiKey !== true) {
            setError("Please configure an LLM provider API key in Settings before enrolling.");
            return;
        }
        if (!subject) {
            setError("Please select a subject.");
            return;
        }
        if (isOther && !customSubject.trim()) {
            setError("Please enter a subject name.");
            return;
        }
        setError("");
        setLoading(true);
        try {
            const { success } = await postRequest("/py/subscribe", {
                skill: finalSubject,
                days,
                hours,
                quiz_difficulty: difficulty,
            });
            if (success) navigate("/syllabi");
        } catch {
            setError("Something went wrong. Please try again.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="h-full overflow-hidden flex flex-col p-4 sm:p-6 md:p-8">
            <div className="max-w-xl mx-auto w-full space-y-5">

                {/* Hero header */}
                <div className="space-y-1">
                    <h1 className="text-2xl font-bold tracking-tight">Start Learning</h1>
                    <p className="text-muted-foreground text-sm">
                        Choose a subject and we'll build a personalised syllabus for you.
                    </p>
                </div>

                {/* No API key banner */}
                {hasApiKey === false && (
                    <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-3.5">
                        <KeyRound className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-amber-800 dark:text-amber-300">API key required</p>
                            <p className="text-xs text-amber-700 dark:text-amber-400 mt-0.5">
                                You need to configure an LLM provider before enrolling. Add your API key in Settings.
                            </p>
                        </div>
                        <Button
                            size="sm"
                            variant="outline"
                            className="shrink-0 border-amber-300 text-amber-700 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900/30 h-8 text-xs"
                            onClick={() => setSettingsOpen(true)}
                        >
                            <Settings className="h-3.5 w-3.5 mr-1.5" />
                            Open Settings
                        </Button>
                    </div>
                )}

                {/* Form card — only shown when API key is configured */}
                {hasApiKey === null && (
                    <div className="flex justify-center py-8">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                )}
                {hasApiKey === true && <div className="rounded-2xl border border-border bg-card shadow-sm">
                    <form onSubmit={handleSubmit}>
                        <div className="p-5 space-y-4">

                            {/* Subject */}
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">Subject</Label>

                                {/* Combobox trigger */}
                                <div ref={dropdownRef} className="relative">
                                    <button
                                        type="button"
                                        aria-haspopup="listbox"
                                        aria-expanded={open}
                                        onClick={() => setOpen((o) => !o)}
                                        onKeyDown={(e) => {
                                            if (e.key === "Escape") setOpen(false);
                                            if (e.key === "ArrowDown" && !open) setOpen(true);
                                        }}
                                        className="w-full flex items-center justify-between rounded-xl border border-input bg-background px-4 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring transition-colors hover:border-ring/50"
                                    >
                                        <span className={subject ? "text-foreground font-medium" : "text-muted-foreground"}>
                                            {subject || "— choose a subject —"}
                                        </span>
                                        <ChevronDown className={cn("h-4 w-4 text-muted-foreground shrink-0 ml-2 transition-transform", open && "rotate-180")} />
                                    </button>

                                    {open && (
                                        <div className="absolute z-50 mt-1.5 w-full rounded-xl border border-border bg-popover shadow-xl overflow-hidden">
                                            <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
                                                <Search className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                                <input
                                                    autoFocus
                                                    aria-label="Search courses"
                                                    className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                                                    placeholder="Search courses…"
                                                    value={search}
                                                    onChange={(e) => setSearch(e.target.value)}
                                                    onKeyDown={(e) => {
                                                        if (e.key === "Escape") { setOpen(false); }
                                                        if (e.key === "ArrowDown") {
                                                            e.preventDefault();
                                                            const list = dropdownRef.current?.querySelector("[role='listbox']");
                                                            (list?.querySelector("[role='option']") as HTMLElement)?.focus();
                                                        }
                                                    }}
                                                />
                                            </div>

                                            <ul role="listbox" className="max-h-52 overflow-y-auto py-1">
                                                {noResults ? (
                                                    <li
                                                        role="option"
                                                        aria-selected={false}
                                                        tabIndex={0}
                                                        onClick={() => selectOther(search)}
                                                        onKeyDown={(e) => {
                                                            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectOther(search); }
                                                            if (e.key === "Escape") setOpen(false);
                                                        }}
                                                        className="px-3 py-4 text-center space-y-1 focus:outline-none focus:bg-accent cursor-pointer"
                                                    >
                                                        <p className="text-sm text-muted-foreground">No courses found for <span className="font-medium text-foreground">"{search}"</span></p>
                                                        <p className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600">
                                                            <PenLine className="h-3.5 w-3.5" />
                                                            Add "{search}" as custom course
                                                        </p>
                                                    </li>
                                                ) : (
                                                    filtered.map((item) => (
                                                        <li
                                                            key={item}
                                                            role="option"
                                                            aria-selected={subject === item && !isOther}
                                                            tabIndex={0}
                                                            onClick={() => selectSubject(item)}
                                                            onKeyDown={(e) => {
                                                                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSubject(item); }
                                                                if (e.key === "Escape") setOpen(false);
                                                                if (e.key === "ArrowDown") { e.preventDefault(); (e.currentTarget.nextElementSibling as HTMLElement)?.focus(); }
                                                                if (e.key === "ArrowUp") {
                                                                    e.preventDefault();
                                                                    const prev = e.currentTarget.previousElementSibling as HTMLElement;
                                                                    if (prev) prev.focus();
                                                                    else dropdownRef.current?.querySelector<HTMLElement>("input")?.focus();
                                                                }
                                                            }}
                                                            className={cn(
                                                                "px-3 py-2 text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none",
                                                                subject === item && !isOther && "bg-accent/50 font-medium"
                                                            )}
                                                        >
                                                            {item}
                                                        </li>
                                                    ))
                                                )}

                                                {!noResults && (
                                                    <li
                                                        role="option"
                                                        aria-selected={isOther}
                                                        tabIndex={0}
                                                        onClick={() => selectOther()}
                                                        onKeyDown={(e) => {
                                                            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectOther(); }
                                                            if (e.key === "Escape") setOpen(false);
                                                            if (e.key === "ArrowDown") { e.preventDefault(); (e.currentTarget.nextElementSibling as HTMLElement)?.focus(); }
                                                            if (e.key === "ArrowUp") {
                                                                e.preventDefault();
                                                                const prev = e.currentTarget.previousElementSibling as HTMLElement;
                                                                if (prev) prev.focus();
                                                                else dropdownRef.current?.querySelector<HTMLElement>("input")?.focus();
                                                            }
                                                        }}
                                                        className={cn(
                                                            "mx-1.5 mb-1 mt-1 flex items-center gap-2 rounded-md border-t border-border pt-2 px-3 py-2 text-sm font-medium cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring",
                                                            isOther
                                                                ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-400"
                                                                : "text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 dark:text-indigo-400"
                                                        )}
                                                    >
                                                        <PenLine className="h-3.5 w-3.5 shrink-0" />
                                                        Other
                                                    </li>
                                                )}
                                            </ul>
                                        </div>
                                    )}
                                </div>

                                {/* Custom subject input */}
                                {isOther && (
                                    <Input
                                        className="mt-2 rounded-xl"
                                        placeholder="e.g. Solidity, Game Development, UX Design…"
                                        value={customSubject}
                                        onChange={(e) => setCustomSubject(e.target.value)}
                                        autoFocus
                                    />
                                )}

                                {/* Quick picks */}
                                {!isOther && (
                                    <div className="flex flex-wrap gap-1.5 pt-1">
                                        {QUICK_PICKS.map((s) => (
                                            <button
                                                key={s}
                                                type="button"
                                                onClick={() => selectSubject(s)}
                                                className={cn(
                                                    "text-xs px-2.5 py-1 rounded-full border transition-all duration-150",
                                                    subject === s
                                                        ? "border-primary bg-primary/10 text-primary font-medium"
                                                        : "border-border text-muted-foreground hover:border-primary/60 hover:text-foreground"
                                                )}
                                            >
                                                {s}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Duration pills */}
                            <div className="space-y-2.5">
                                <div className="flex items-center gap-2">
                                    <CalendarDays className="h-4 w-4 text-muted-foreground" />
                                    <Label className="text-sm font-medium">Duration</Label>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {DAY_OPTIONS.map((d) => (
                                        <button
                                            key={d.value}
                                            type="button"
                                            onClick={() => setDays(d.value)}
                                            className={cn(
                                                "px-4 py-2 rounded-xl border text-sm font-medium transition-all duration-150",
                                                days === d.value
                                                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                                                    : "border-border bg-background hover:border-primary/50 hover:bg-muted text-foreground"
                                            )}
                                        >
                                            {d.label}
                                        </button>
                                    ))}
                                    <div className="flex items-center gap-1.5">
                                        <Input
                                            type="number"
                                            min={1}
                                            max={365}
                                            placeholder="Custom"
                                            value={DAY_OPTIONS.some((d) => d.value === days) ? "" : days}
                                            onChange={(e) => {
                                                const v = parseInt(e.target.value, 10)
                                                if (!isNaN(v)) setDays(Math.min(365, Math.max(1, v)))
                                            }}
                                            className="w-24 h-9 rounded-xl text-sm text-center"
                                        />
                                        <span className="text-xs text-muted-foreground">days</span>
                                    </div>
                                </div>
                            </div>

                            {/* Daily commitment pills */}
                            <div className="space-y-2.5">
                                <div className="flex items-center gap-2">
                                    <Clock className="h-4 w-4 text-muted-foreground" />
                                    <Label className="text-sm font-medium">Daily commitment</Label>
                                </div>
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                                    {HOUR_OPTIONS.map((h) => (
                                        <button
                                            key={h.value}
                                            type="button"
                                            onClick={() => setHours(h.value)}
                                            className={cn(
                                                "flex flex-col items-center justify-center py-3 rounded-xl border text-sm transition-all duration-150",
                                                hours === h.value
                                                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                                                    : "border-border bg-background hover:border-primary/50 hover:bg-muted text-foreground"
                                            )}
                                        >
                                            <span className="text-lg font-bold leading-none">{h.value}</span>
                                            <span className="text-xs mt-0.5 opacity-70">{h.value > 1 ? "hrs" : "hr"}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Quiz difficulty */}
                            <div className="space-y-2.5">
                                <Label className="text-sm font-medium">Quiz difficulty</Label>
                                <p className="text-xs text-muted-foreground -mt-1">
                                    Sets how hard the end-of-course quiz will be.
                                </p>
                                <div className="grid grid-cols-3 gap-2">
                                    {DIFFICULTY_OPTIONS.map((d) => (
                                        <button
                                            key={d.value}
                                            type="button"
                                            onClick={() => setDifficulty(d.value)}
                                            className={cn(
                                                "flex flex-col items-center justify-center py-3 rounded-xl border text-sm transition-all duration-150",
                                                difficulty === d.value
                                                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                                                    : "border-border bg-background hover:border-primary/50 hover:bg-muted text-foreground"
                                            )}
                                        >
                                            <span className="font-semibold leading-none">{d.label}</span>
                                            <span className="text-xs mt-1 opacity-70">{d.desc}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>

                        </div>

                        {/* Footer */}
                        <div className="border-t border-border px-6 py-4 bg-muted/30 rounded-b-2xl space-y-3">
                            {error && <p className="text-sm text-destructive">{error}</p>}
                            <Button type="submit" className="w-full h-10 rounded-xl" disabled={loading || hasApiKey !== true}>
                                {loading ? (
                                    <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Enrolling…</>
                                ) : (
                                    <><UserPlus className="h-4 w-4 mr-2" />Enroll</>
                                )}
                            </Button>
                        </div>
                    </form>
                </div>}

            </div>
        </div>
    );
}
