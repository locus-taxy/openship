import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { UserPlus, ChevronDown, Loader2, Search, PenLine } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { postRequest } from "@/services";
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

const DAY_OPTIONS = [30, 60, 90, 120, 180];
const HOUR_OPTIONS = [1, 2, 3, 4];

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
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const { setPluginName } = useStore((state: any) => state);
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
            });
            if (success) navigate("/syllabi");
        } catch {
            setError("Something went wrong. Please try again.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="p-6 max-w-lg space-y-6">
            <div>
                <h1 className="text-2xl font-bold tracking-tight">Start Learning</h1>
                <p className="text-muted-foreground mt-1">
                    Choose a subject and we'll build a personalised syllabus for you.
                </p>
            </div>

            <Card>
                <CardHeader className="pb-2">
                    <p className="text-sm font-medium">New enrollment</p>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div className="space-y-1.5">
                            <Label>Subject</Label>

                            {/* Trigger button */}
                            <div ref={dropdownRef} className="relative">
                                <button
                                    type="button"
                                    aria-haspopup="listbox"
                                    aria-expanded={open}
                                    onClick={() => setOpen((o) => !o)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Escape") setOpen(false);
                                        if ((e.key === "ArrowDown" || e.key === "Enter") && !open) setOpen(true);
                                    }}
                                    className="w-full flex items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                                >
                                    <span className={subject ? "text-foreground" : "text-muted-foreground"}>
                                        {subject || "— choose a subject —"}
                                    </span>
                                    <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
                                </button>

                                {/* Dropdown */}
                                {open && (
                                    <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-lg">
                                        {/* Search box */}
                                        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
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
                                                <li role="option" aria-selected={false} className="px-3 py-4 text-center space-y-2">
                                                    <p className="text-sm text-muted-foreground">No courses found for <span className="font-medium text-foreground">"{search}"</span></p>
                                                    <button
                                                        type="button"
                                                        onClick={() => selectOther(search)}
                                                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") selectOther(search); }}
                                                        className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700"
                                                    >
                                                        <PenLine className="h-3.5 w-3.5" />
                                                        Add "{search}" as custom course
                                                    </button>
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
                                                        className={`px-3 py-2 text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground focus:outline-none ${subject === item && !isOther ? "bg-accent/50 font-medium" : ""}`}
                                                    >
                                                        {item}
                                                    </li>
                                                ))
                                            )}
                                        </ul>

                                        {/* Other — always visible at the bottom unless no-results is showing it */}
                                        {!noResults && (
                                            <div className="border-t border-border p-1.5">
                                                <button
                                                    type="button"
                                                    role="option"
                                                    aria-selected={isOther}
                                                    onClick={() => selectOther()}
                                                    onKeyDown={(e) => {
                                                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectOther(); }
                                                        if (e.key === "Escape") setOpen(false);
                                                        if (e.key === "ArrowUp") {
                                                            e.preventDefault();
                                                            const list = dropdownRef.current?.querySelector("[role='listbox']");
                                                            (list?.lastElementChild as HTMLElement)?.focus();
                                                        }
                                                    }}
                                                    className={`w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring
                                                        ${isOther
                                                            ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-400"
                                                            : "text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 dark:text-indigo-400"
                                                        }`}
                                                >
                                                    <PenLine className="h-3.5 w-3.5 shrink-0" />
                                                    Other — type your own
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Custom subject input */}
                            {isOther && (
                                <Input
                                    className="mt-2"
                                    placeholder="e.g. Solidity, Game Development, UX Design…"
                                    value={customSubject}
                                    onChange={(e) => setCustomSubject(e.target.value)}
                                    autoFocus
                                />
                            )}
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <Label htmlFor="days">Duration</Label>
                                <div className="relative">
                                    <select
                                        id="days"
                                        className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2 pr-9 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                                        value={days}
                                        onChange={(e) => setDays(Number(e.target.value))}
                                    >
                                        {DAY_OPTIONS.map((d) => (
                                            <option key={d} value={d}>
                                                {d} days
                                            </option>
                                        ))}
                                    </select>
                                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                </div>
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="hours">Daily commitment</Label>
                                <div className="relative">
                                    <select
                                        id="hours"
                                        className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2 pr-9 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                                        value={hours}
                                        onChange={(e) => setHours(Number(e.target.value))}
                                    >
                                        {HOUR_OPTIONS.map((h) => (
                                            <option key={h} value={h}>
                                                {h} hr{h > 1 ? "s" : ""} / day
                                            </option>
                                        ))}
                                    </select>
                                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                </div>
                            </div>
                        </div>

                        {error && <p className="text-sm text-destructive">{error}</p>}

                        <Button type="submit" className="w-full" disabled={loading}>
                            {loading ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Enrolling…
                                </>
                            ) : (
                                <>
                                    <UserPlus className="h-4 w-4 mr-2" /> Enroll
                                </>
                            )}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
