import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Eye, EyeOff } from "lucide-react";
import { toast } from "@/hooks/use-toast";
import useAuthStore from "@/store/authStore";

export default function LoginPage() {
    const navigate = useNavigate();
    const { login, isAuthenticated, initAuth, sessionExpired, clearSessionExpired } = useAuthStore();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        initAuth();
    }, []);

    useEffect(() => {
        if (isAuthenticated) {
            navigate("/", { replace: true });
        }
    }, [isAuthenticated, navigate]);

    useEffect(() => {
        if (sessionExpired) {
            toast({
                variant: "destructive",
                title: "Session expired",
                description: "Please sign in again to continue.",
            });
            clearSessionExpired();
        }
    }, [sessionExpired, clearSessionExpired]);

    useEffect(() => {
        const root = document.documentElement;
        const wasDark = root.classList.contains("dark");
        root.classList.remove("dark");
        return () => { if (wasDark) root.classList.add("dark"); };
    }, []);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            await login(email, password);
            navigate("/", { replace: true });
        } catch (err: any) {
            setError(err?.response?.data?.detail || "Login failed");
        } finally {
            setLoading(false);
        }
    }

    if (isAuthenticated) return null;

    return (
        <div className="flex min-h-screen items-center justify-center bg-zinc-800 px-4">
            <div className="w-full max-w-sm space-y-6">
                <div className="text-center">
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent">
                        Openship
                    </h1>
                    <p className="mt-2 text-sm text-zinc-400">
                        Your AI-powered learning companion
                    </p>
                </div>

                <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl">
                    <form onSubmit={handleSubmit} className="grid gap-4">
                        <div className="grid gap-2">
                            <Label htmlFor="email">Email</Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="you@example.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="password">Password</Label>
                            <div className="relative">
                                <Input
                                    id="password"
                                    type={showPassword ? "text" : "password"}
                                    placeholder="Enter your password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    className="pr-10"
                                />
                                <button
                                    type="button"
                                    tabIndex={-1}
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 transition-colors"
                                >
                                    {showPassword ? (
                                        <EyeOff className="h-4 w-4" />
                                    ) : (
                                        <Eye className="h-4 w-4" />
                                    )}
                                </button>
                            </div>
                        </div>

                        {error && (
                            <p className="text-sm text-destructive">{error}</p>
                        )}

                        <Button
                            type="submit"
                            className="w-full mt-1 bg-zinc-900 text-white hover:bg-zinc-800"
                            disabled={loading}
                        >
                            {loading ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                "Sign in"
                            )}
                        </Button>
                    </form>

                    <p className="mt-4 text-center text-sm text-zinc-500">
                        Don't have an account?{" "}
                        <Link
                            to="/signup"
                            className="text-zinc-900 font-medium underline underline-offset-4 hover:text-zinc-600 transition-colors"
                        >
                            Sign up
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
