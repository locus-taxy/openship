import { useState } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";
import useAuthStore from "@/store/authStore";
import useAuthDialogStore from "@/store/authDialogStore";

function LoginView() {
    const { login } = useAuthStore();
    const { close, switchView } = useAuthDialogStore();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            await login(email, password);
            close();
        } catch (err: any) {
            setError(err?.response?.data?.detail || "Login failed");
        } finally {
            setLoading(false);
        }
    }

    return (
        <>
            <DialogHeader>
                <DialogTitle>Welcome back</DialogTitle>
                <DialogDescription>
                    Sign in to your Openship account
                </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="grid gap-4 pt-2">
                <div className="grid gap-2">
                    <Label htmlFor="login-email">Email</Label>
                    <Input
                        id="login-email"
                        type="email"
                        placeholder="you@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                </div>
                <div className="grid gap-2">
                    <Label htmlFor="login-password">Password</Label>
                    <Input
                        id="login-password"
                        type="password"
                        placeholder="Min. 8 characters"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                    />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
                </Button>
                <p className="text-center text-sm text-muted-foreground">
                    Don't have an account?{" "}
                    <button
                        type="button"
                        className="underline underline-offset-4 hover:text-primary"
                        onClick={() => switchView("signup")}
                    >
                        Sign up
                    </button>
                </p>
            </form>
        </>
    );
}

function SignupView() {
    const { signup } = useAuthStore();
    const { close, switchView } = useAuthDialogStore();
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    const [success, setSuccess] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (password.length < 8) {
            setError("Password must be at least 8 characters");
            return;
        }
        setError("");
        setLoading(true);
        try {
            await signup(name, email, password);
            setSuccess(true);
            setTimeout(() => {
                setSuccess(false);
                switchView("login");
            }, 1500);
        } catch (err: any) {
            setError(err?.response?.data?.detail || "Signup failed");
        } finally {
            setLoading(false);
        }
    }

    return (
        <>
            <DialogHeader>
                <DialogTitle>Create an account</DialogTitle>
                <DialogDescription>
                    Get started with Openship
                </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="grid gap-4 pt-2">
                <div className="grid gap-2">
                    <Label htmlFor="signup-name">Name</Label>
                    <Input
                        id="signup-name"
                        type="text"
                        placeholder="Your name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                    />
                </div>
                <div className="grid gap-2">
                    <Label htmlFor="signup-email">Email</Label>
                    <Input
                        id="signup-email"
                        type="email"
                        placeholder="you@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                    />
                </div>
                <div className="grid gap-2">
                    <Label htmlFor="signup-password">Password</Label>
                    <Input
                        id="signup-password"
                        type="password"
                        placeholder="Min. 8 characters"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        minLength={8}
                    />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                {success && <p className="text-sm text-green-600">Account created! Redirecting to sign in...</p>}
                <Button type="submit" className="w-full" disabled={loading || success}>
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create account"}
                </Button>
                <p className="text-center text-sm text-muted-foreground">
                    Already have an account?{" "}
                    <button
                        type="button"
                        className="underline underline-offset-4 hover:text-primary"
                        onClick={() => switchView("login")}
                    >
                        Sign in
                    </button>
                </p>
            </form>
        </>
    );
}

export default function AuthDialog() {
    const { isOpen, view, close } = useAuthDialogStore();

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
            <DialogContent className="sm:max-w-md">
                {view === "login" ? <LoginView /> : <SignupView />}
            </DialogContent>
        </Dialog>
    );
}
