import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import useAuthStore from "@/store/authStore";

export default function SignupPage() {
    const navigate = useNavigate();
    const { signup, isAuthenticated, initialized, initAuth } = useAuthStore();
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        initAuth();
    }, []);

    useEffect(() => {
        if (initialized && isAuthenticated) {
            navigate("/", { replace: true });
        }
    }, [initialized, isAuthenticated, navigate]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (password.length < 8) {
            setError("Password must be at least 8 characters");
            return;
        }
        if (password !== confirmPassword) {
            setError("Passwords do not match");
            return;
        }
        setError("");
        setLoading(true);
        try {
            await signup(name, email, password);
            setSuccess(true);
            setTimeout(() => {
                navigate("/login");
            }, 1500);
        } catch (err: any) {
            setError(err?.response?.data?.detail || "Signup failed");
        } finally {
            setLoading(false);
        }
    }

    if (!initialized) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-zinc-950">
                <Loader2 className="h-8 w-8 animate-spin text-zinc-400" />
            </div>
        );
    }

    if (isAuthenticated) return null;

    return (
        <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
            <div className="w-full max-w-sm space-y-6">
                <div className="text-center">
                    <h1 className="text-3xl font-bold text-white">Openship</h1>
                    <p className="mt-2 text-sm text-zinc-400">
                        Create your account
                    </p>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-6 shadow-2xl backdrop-blur">
                    <form onSubmit={handleSubmit} className="grid gap-4">
                        <div className="grid gap-2">
                            <Label htmlFor="name" className="text-zinc-300">
                                Name
                            </Label>
                            <Input
                                id="name"
                                type="text"
                                placeholder="Your name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                                className="bg-zinc-800/50 border-zinc-700 text-white placeholder:text-zinc-500 focus-visible:ring-zinc-600"
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="email" className="text-zinc-300">
                                Email
                            </Label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="you@example.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                                className="bg-zinc-800/50 border-zinc-700 text-white placeholder:text-zinc-500 focus-visible:ring-zinc-600"
                            />
                        </div>

                        <div className="grid gap-2">
                            <Label htmlFor="password" className="text-zinc-300">
                                Password
                            </Label>
                            <div className="relative">
                                <Input
                                    id="password"
                                    type={showPassword ? "text" : "password"}
                                    placeholder="Min. 8 characters"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    minLength={8}
                                    className="bg-zinc-800/50 border-zinc-700 text-white placeholder:text-zinc-500 focus-visible:ring-zinc-600 pr-10"
                                />
                                <button
                                    type="button"
                                    tabIndex={-1}
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                                >
                                    {showPassword ? (
                                        <EyeOff className="h-4 w-4" />
                                    ) : (
                                        <Eye className="h-4 w-4" />
                                    )}
                                </button>
                            </div>
                        </div>

                        <div className="grid gap-2">
                            <Label
                                htmlFor="confirm-password"
                                className="text-zinc-300"
                            >
                                Confirm Password
                            </Label>
                            <div className="relative">
                                <Input
                                    id="confirm-password"
                                    type={
                                        showConfirmPassword
                                            ? "text"
                                            : "password"
                                    }
                                    placeholder="Re-enter your password"
                                    value={confirmPassword}
                                    onChange={(e) =>
                                        setConfirmPassword(e.target.value)
                                    }
                                    required
                                    minLength={8}
                                    className="bg-zinc-800/50 border-zinc-700 text-white placeholder:text-zinc-500 focus-visible:ring-zinc-600 pr-10"
                                />
                                <button
                                    type="button"
                                    tabIndex={-1}
                                    onClick={() =>
                                        setShowConfirmPassword(
                                            !showConfirmPassword
                                        )
                                    }
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                                >
                                    {showConfirmPassword ? (
                                        <EyeOff className="h-4 w-4" />
                                    ) : (
                                        <Eye className="h-4 w-4" />
                                    )}
                                </button>
                            </div>
                        </div>

                        {error && (
                            <p className="text-sm text-red-400">{error}</p>
                        )}
                        {success && (
                            <p className="flex items-center gap-1.5 text-sm text-emerald-400">
                                <CheckCircle2 className="h-4 w-4" />
                                Account created! Redirecting to sign in...
                            </p>
                        )}

                        <Button
                            type="submit"
                            className="w-full mt-1"
                            disabled={loading || success}
                        >
                            {loading ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                                "Create account"
                            )}
                        </Button>
                    </form>

                    <p className="mt-4 text-center text-sm text-zinc-500">
                        Already have an account?{" "}
                        <Link
                            to="/login"
                            className="text-white underline underline-offset-4 hover:text-zinc-300 transition-colors"
                        >
                            Sign in
                        </Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
