import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { UserPlus, ChevronDown, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
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

export default function SubscribePage() {
    const navigate = useNavigate();
    const [subject, setSubject] = useState("");
    const [days, setDays] = useState(90);
    const [hours, setHours] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const { setPluginName } = useStore((state: any) => state);

    useEffect(() => {
        setPluginName("Subscribe");
    }, [setPluginName]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!subject) {
            setError("Please select a subject.");
            return;
        }
        setError("");
        setLoading(true);
        const { success } = await postRequest("/py/subscribe", {
            skill: subject,
            days,
            hours,
        });
        setLoading(false);
        if (success) navigate("/syllabi");
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
                    <p className="text-sm font-medium">New subscription</p>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div className="space-y-1.5">
                            <Label htmlFor="subject">Subject</Label>
                            <div className="relative">
                                <select
                                    id="subject"
                                    className="w-full appearance-none rounded-md border border-input bg-background px-3 py-2 pr-9 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                                    value={subject}
                                    onChange={(e) => setSubject(e.target.value)}
                                    required
                                >
                                    <option value="">— choose a subject —</option>
                                    {SUBJECTS.map((group) => (
                                        <optgroup key={group.group} label={group.group}>
                                            {group.items.map((item) => (
                                                <option key={item} value={item}>
                                                    {item}
                                                </option>
                                            ))}
                                        </optgroup>
                                    ))}
                                </select>
                                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            </div>
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
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" /> Subscribing…
                                </>
                            ) : (
                                <>
                                    <UserPlus className="h-4 w-4 mr-2" /> Subscribe
                                </>
                            )}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
