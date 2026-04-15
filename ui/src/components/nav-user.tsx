import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { SidebarMenu, SidebarMenuItem } from "@/components/ui/sidebar";
import { Button } from "./ui/button";
import { LogOutIcon, UserCircle, Settings, Eye, EyeOff, KeyRound, CheckCircle2, Loader2, X } from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import useAuthStore from "@/store/authStore";
import useStore from "@/store";
import { ThemeToggle } from "./theme-toggle";
import { getRequest, putRequest } from "@/services";

export function NavUser() {
    const { user, isAuthenticated, logout } = useAuthStore();
    const navigate = useNavigate();
    const { toast } = useToast();
    const { settingsOpen, setSettingsOpen } = useStore((s: any) => s);

    const [apiKey, setApiKey] = useState("");
    const [hasKey, setHasKey] = useState(false);
    const [showKey, setShowKey] = useState(false);
    const [saving, setSaving] = useState(false);
    const [removing, setRemoving] = useState(false);

    useEffect(() => {
        if (!settingsOpen) return;
        getRequest("/py/auth/me/settings").then(({ success, data }) => {
            if (success) setHasKey(data.has_gemini_api_key);
        });
        setApiKey("");
        setShowKey(false);
    }, [settingsOpen]);

    if (!isAuthenticated || !user) return null;

    function handleLogout() {
        logout();
        navigate("/login");
    }

    async function handleSave() {
        if (!apiKey.trim()) return;
        setSaving(true);
        const { success } = await putRequest("/py/auth/me/settings", { gemini_api_key: apiKey.trim() });
        setSaving(false);
        if (success) {
            setHasKey(true);
            setApiKey("");
            setSettingsOpen(false);
            toast({ title: "API key saved", description: "Your Gemini API key has been saved." });
        }
    }

    async function handleRemove() {
        setRemoving(true);
        const { success } = await putRequest("/py/auth/me/settings", { gemini_api_key: null });
        setRemoving(false);
        if (success) {
            setHasKey(false);
            setApiKey("");
            toast({ title: "API key removed" });
        }
    }

    return (
        <>
            <SidebarMenu>
                <SidebarMenuItem>
                    <div className="flex items-center gap-2 px-2 py-2">
                        <UserCircle className="h-6 w-6 text-muted-foreground" />
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{user.name}</p>
                            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                        </div>
                        <button
                            onClick={() => setSettingsOpen(true)}
                            title="Settings"
                            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        >
                            <Settings className="h-4 w-4" />
                        </button>
                        <ThemeToggle />
                    </div>
                    <hr className="my-1" />
                    <Button variant="outline" className="w-full mt-1" onClick={handleLogout}>
                        <LogOutIcon className="w-4 h-4 mr-2" />
                        Logout
                    </Button>
                </SidebarMenuItem>
            </SidebarMenu>

            <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
                <DialogContent className="max-w-md p-0 gap-0 overflow-hidden">
                    <DialogHeader className="px-6 pt-6 pb-4 border-b bg-muted/30">
                        <div className="flex items-center justify-between">
                            <DialogTitle className="text-base font-semibold flex items-center gap-2">
                                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                                    <Settings className="h-4 w-4" />
                                </div>
                                Settings
                            </DialogTitle>
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                            Configure your account preferences
                        </p>
                    </DialogHeader>

                    <div className="px-6 py-5 space-y-5">

                        {/* Section: Gemini API Key */}
                        <div className="space-y-3">
                            <div className="flex items-center gap-2">
                                <KeyRound className="h-4 w-4 text-muted-foreground" />
                                <p className="text-sm font-medium">Gemini API Key</p>
                            </div>

                            {/* Status badge */}
                            <div className={cn(
                                "flex items-center gap-3 rounded-xl border px-4 py-3",
                                hasKey
                                    ? "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30"
                                    : "border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30"
                            )}>
                                <div className={cn(
                                    "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
                                    hasKey ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/50" : "bg-amber-100 text-amber-600 dark:bg-amber-900/50"
                                )}>
                                    {hasKey ? <CheckCircle2 className="h-4 w-4" /> : <KeyRound className="h-4 w-4" />}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className={cn(
                                        "text-sm font-medium",
                                        hasKey ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"
                                    )}>
                                        {hasKey ? "API key is configured" : "No API key set"}
                                    </p>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                        {hasKey ? "Your key is securely stored" : "Required to generate syllabi and content"}
                                    </p>
                                </div>
                                {hasKey && (
                                    <button
                                        onClick={handleRemove}
                                        disabled={removing}
                                        title="Remove key"
                                        className="shrink-0 p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                                    >
                                        {removing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
                                    </button>
                                )}
                            </div>

                            {/* Input */}
                            <div className="space-y-1.5">
                                <p className="text-xs text-muted-foreground font-medium">
                                    {hasKey ? "Replace with a new key" : "Enter your API key"}
                                </p>
                                <div className="relative">
                                    <Input
                                        type={showKey ? "text" : "password"}
                                        placeholder="AIzaSy..."
                                        value={apiKey}
                                        onChange={(e) => setApiKey(e.target.value)}
                                        className="pr-10 font-mono text-sm"
                                        onKeyDown={(e) => { if (e.key === "Enter") handleSave(); }}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowKey((v) => !v)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                                    >
                                        {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                    </button>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    Get your free key from{" "}
                                    <a
                                        href="https://aistudio.google.com/app/apikey"
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-primary underline-offset-4 hover:underline font-medium"
                                    >
                                        Google AI Studio →
                                    </a>
                                </p>
                            </div>

                            <Button
                                onClick={handleSave}
                                disabled={saving || !apiKey.trim()}
                                className="w-full"
                            >
                                {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : "Save API Key"}
                            </Button>
                        </div>

                    </div>
                </DialogContent>
            </Dialog>
        </>
    );
}
