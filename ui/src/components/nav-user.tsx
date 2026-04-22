import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { SidebarMenu, SidebarMenuItem } from "@/components/ui/sidebar";
import { Button } from "./ui/button";
import {
    LogOutIcon, UserCircle, Settings, Eye, EyeOff,
    KeyRound, CheckCircle2, Loader2, X, ChevronDown, Pencil, Trash2,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import useAuthStore from "@/store/authStore";
import useStore from "@/store";
import { ThemeToggle } from "./theme-toggle";
import { getRequest, putRequest, postRequest } from "@/services";

interface Provider { value: string; label: string }

const PROVIDER_DOCS: Record<string, string> = {
    gemini: "https://aistudio.google.com/app/apikey",
    openai: "https://platform.openai.com/api-keys",
    anthropic: "https://console.anthropic.com/settings/keys",
    mistral: "https://console.mistral.ai/api-keys",
};

interface SettingsData {
    llm_provider: string | null;
    llm_model: string | null;
    provider_keys: Record<string, boolean>;
    supported_providers: Provider[];
    provider_models: Record<string, string[]>;
}

export function NavUser() {
    const { user, isAuthenticated, logout } = useAuthStore();
    const navigate = useNavigate();
    const { toast } = useToast();
    const { settingsOpen, setSettingsOpen, pendingProvider, setPendingProvider } = useStore((s: any) => s);

    const [settings, setSettings] = useState<SettingsData | null>(null);
    const [selectedProvider, setSelectedProvider] = useState("");
    const [selectedModel, setSelectedModel] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [editingKey, setEditingKey] = useState(false);  // controls whether key input is shown
    const [showKey, setShowKey] = useState(false);
    const [saving, setSaving] = useState(false);
    const [removing, setRemoving] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [providerOpen, setProviderOpen] = useState(false);
    const [modelOpen, setModelOpen] = useState(false);
    const [liveModels, setLiveModels] = useState<Record<string, string[]>>({});
    const [loadingModels, setLoadingModels] = useState(false);
    const [customModelInput, setCustomModelInput] = useState("");
    const [showCustomModel, setShowCustomModel] = useState(false);
    const [verifying, setVerifying] = useState(false);
    const [verifyResult, setVerifyResult] = useState<{ ok: boolean; reason?: string } | null>(null);
    const [modelSearch, setModelSearch] = useState("");

    async function loadSettings() {
        const { success, data } = await getRequest("/py/auth/me/settings");
        if (success) {
            setSettings(data);
            setSelectedProvider(data.llm_provider ?? "");
            setSelectedModel(data.llm_model ?? "");
        }
    }

    async function loadModelsForProvider(provider: string) {
        if (!provider) return;
        setLoadingModels(true);
        const { success, data } = await getRequest(`/py/auth/me/models?provider=${provider}`);
        setLoadingModels(false);
        if (success && data.models?.length) {
            setLiveModels(prev => ({ ...prev, [provider]: data.models }));
        }
    }

    useEffect(() => {
        if (!settingsOpen) return;
        loadSettings().then(() => {
            if (pendingProvider) {
                setSelectedProvider(pendingProvider);
                setPendingProvider(null);
            }
        });
        setApiKey("");
        setEditingKey(false);
        setShowKey(false);
        setConfirmDelete(false);
    }, [settingsOpen]);

    // When provider changes: fetch live models, reset editing state
    useEffect(() => {
        if (!settings || !selectedProvider) return;
        setEditingKey(false);
        setApiKey("");
        setConfirmDelete(false);
        setShowCustomModel(false);
        setCustomModelInput("");
        setVerifyResult(null);
        setModelSearch("");
        loadModelsForProvider(selectedProvider);
        const fallbackModels = settings.provider_models[selectedProvider] ?? [];
        const current = settings.llm_provider === selectedProvider ? settings.llm_model : null;
        setSelectedModel(current || fallbackModels[0] || "");
    }, [selectedProvider]);

    if (!isAuthenticated || !user) return null;

    function handleLogout() { logout(); navigate("/login"); }

    const currentProviderHasKey = settings?.provider_keys?.[selectedProvider] ?? false;
    const providerLabel = (p: string) => settings?.supported_providers.find(s => s.value === p)?.label ?? p;
    // Prefer live-fetched models, fall back to static list from settings
    const availableModels = liveModels[selectedProvider] ?? settings?.provider_models?.[selectedProvider] ?? [];
    const filteredModels = modelSearch
        ? availableModels.filter(m => m.toLowerCase().includes(modelSearch.toLowerCase()))
        : availableModels;

    async function handleVerifyAndUseModel() {
        const m = customModelInput.trim();
        if (!m || !selectedProvider) return;
        setVerifying(true);
        setVerifyResult(null);
        const { success, data } = await postRequest(
            `/py/auth/me/models/verify?provider=${selectedProvider}&model=${encodeURIComponent(m)}`, {}
        );
        setVerifying(false);
        if (!success) {
            setVerifyResult({ ok: false, reason: "Verification request failed." });
            return;
        }
        if (data.ok) {
            setSelectedModel(m);
            setShowCustomModel(false);
            setCustomModelInput("");
            setVerifyResult(null);
        } else {
            setVerifyResult({ ok: false, reason: data.reason });
        }
    }

    async function handleSave() {
        if (!selectedProvider) return;
        if (!currentProviderHasKey && !apiKey.trim()) return;
        if (editingKey && !apiKey.trim()) return;
        setSaving(true);
        const body: Record<string, string | null> = {
            llm_provider: selectedProvider,
            llm_model: selectedModel || null,
        };
        if (apiKey.trim()) body.api_key = apiKey.trim();
        const { success } = await putRequest("/py/auth/me/settings", body);
        setSaving(false);
        if (success) {
            await loadSettings();
            setApiKey("");
            setEditingKey(false);
            setSettingsOpen(false);
            toast({ title: "Settings saved", description: `${providerLabel(selectedProvider)} configured.` });
        }
    }

    async function handleRemoveKey() {
        if (!selectedProvider) return;
        setRemoving(true);
        try {
            const { success } = await putRequest("/py/auth/me/settings", {
                llm_provider: selectedProvider,
                api_key: "",
                llm_model: selectedModel || null,
            });
            if (success) {
                setConfirmDelete(false);
                setEditingKey(false);
                await loadSettings();
                toast({ title: "API key removed", description: `${providerLabel(selectedProvider)} key cleared.` });
            } else {
                toast({ title: "Failed to remove key", description: "Please try again.", variant: "destructive" });
            }
        } finally {
            setRemoving(false);
        }
    }

    const configuredProviders = Object.entries(settings?.provider_keys ?? {})
        .filter(([, v]) => v)
        .map(([k]) => k);

    const showKeyInput = !currentProviderHasKey || editingKey;

    const [activeTab, setActiveTab] = useState<"llm" | "account">("llm");

    const NAV_ITEMS = [
        { id: "llm" as const,     label: "LLM",     icon: Settings },
        { id: "account" as const, label: "Account",  icon: UserCircle },
    ];

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
                            onClick={() => { setActiveTab("llm"); setSettingsOpen(true); }}
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
                <DialogContent className="w-[95vw] max-w-2xl h-[90vh] sm:h-[520px] p-0 gap-0 overflow-hidden flex flex-col">
                    <div className="flex flex-1 overflow-hidden">

                        {/* Left nav */}
                        <div className="w-20 sm:w-44 shrink-0 border-r bg-muted/30 flex flex-col py-3 px-1.5 sm:px-3 gap-0.5">
                            <p className="text-[10px] sm:text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2 mb-1.5">Settings</p>
                            {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
                                <button
                                    key={id}
                                    onClick={() => setActiveTab(id)}
                                    className={cn(
                                        "flex flex-col sm:flex-row items-center sm:gap-2 px-1.5 sm:px-3 py-2 rounded-lg text-[10px] sm:text-sm font-medium transition-colors w-full text-center sm:text-left",
                                        activeTab === id
                                            ? "bg-background text-foreground shadow-sm"
                                            : "text-muted-foreground hover:text-foreground hover:bg-background/60"
                                    )}
                                >
                                    <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4 shrink-0 mb-0.5 sm:mb-0" />
                                    {label}
                                </button>
                            ))}
                        </div>

                        {/* Right content */}
                        <div className="flex-1 overflow-y-auto">

                            {/* ── LLM tab ── */}
                            {activeTab === "llm" && (
                                <div className="px-3 sm:px-8 py-4 sm:py-7 space-y-4 sm:space-y-6">
                                    <div>
                                        <h2 className="text-sm sm:text-base font-semibold">LLM Settings</h2>
                                        <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">Each provider's key is saved separately.</p>
                                    </div>

                                    {/* Configured provider pills */}
                                    {configuredProviders.length > 0 && (
                                        <div className="flex flex-wrap gap-1">
                                            {configuredProviders.map(p => (
                                                <span key={p} className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30 px-2 py-0.5 text-[10px] sm:text-xs font-medium text-emerald-700 dark:text-emerald-400">
                                                    <CheckCircle2 className="h-2.5 w-2.5" />
                                                    {providerLabel(p)}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    {/* Provider selector */}
                                    <div className="space-y-1.5">
                                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Provider</p>
                                        <div className="relative">
                                            <button
                                                type="button"
                                                onClick={() => { setProviderOpen(o => !o); setModelOpen(false); }}
                                                className="w-full flex items-center justify-between rounded-xl border border-input bg-background px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring transition-colors hover:border-ring/50"
                                            >
                                                <span className={selectedProvider ? "text-foreground font-medium" : "text-muted-foreground"}>
                                                    {selectedProvider ? providerLabel(selectedProvider) : "Select a provider"}
                                                </span>
                                                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", providerOpen && "rotate-180")} />
                                            </button>
                                            {providerOpen && (
                                                <div className="absolute z-50 mt-1 w-full rounded-xl border border-border bg-popover shadow-lg overflow-hidden">
                                                    {(settings?.supported_providers ?? []).map(p => (
                                                        <button
                                                            key={p.value}
                                                            type="button"
                                                            onClick={() => { setSelectedProvider(p.value); setProviderOpen(false); }}
                                                            className={cn(
                                                                "w-full flex items-center gap-3 px-3 py-2.5 text-sm text-left hover:bg-accent transition-colors",
                                                                selectedProvider === p.value && "bg-accent/50 font-medium"
                                                            )}
                                                        >
                                                            <span className="flex-1">{p.label}</span>
                                                            {settings?.provider_keys?.[p.value]
                                                                ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                                                                : <KeyRound className="h-3.5 w-3.5 text-muted-foreground/40" />
                                                            }
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {selectedProvider && (
                                        <>
                                            {/* Model selector */}
                                            {availableModels.length > 0 && (
                                                <div className="space-y-1.5">
                                                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Model</p>
                                                    <div className="relative">
                                                        <button
                                                            type="button"
                                                            onClick={() => { setModelOpen(o => !o); setProviderOpen(false); setModelSearch(""); }}
                                                            disabled={loadingModels}
                                                            className="w-full flex items-center justify-between rounded-xl border border-input bg-background px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring transition-colors hover:border-ring/50 disabled:opacity-60"
                                                        >
                                                            <span className="font-mono text-xs sm:text-sm truncate">{selectedModel || availableModels[0]}</span>
                                                            {loadingModels
                                                                ? <Loader2 className="h-4 w-4 text-muted-foreground animate-spin" />
                                                                : <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", modelOpen && "rotate-180")} />
                                                            }
                                                        </button>
                                                        {modelOpen && (
                                                            <div className="absolute z-50 mt-1 w-full rounded-xl border border-border bg-popover shadow-lg overflow-hidden">
                                                                <div className="p-2 border-b border-border">
                                                                    <input
                                                                        type="text"
                                                                        placeholder="Search models…"
                                                                        value={modelSearch}
                                                                        onChange={e => setModelSearch(e.target.value)}
                                                                        onClick={e => e.stopPropagation()}
                                                                        autoFocus
                                                                        className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                                                                    />
                                                                </div>
                                                                <div className="max-h-24 overflow-y-auto">
                                                                    {filteredModels.map(m => (
                                                                        <button
                                                                            key={m}
                                                                            type="button"
                                                                            onClick={() => { setSelectedModel(m); setModelOpen(false); setModelSearch(""); }}
                                                                            className={cn(
                                                                                "w-full flex items-center gap-3 px-3 py-2.5 text-sm font-mono text-left hover:bg-accent transition-colors",
                                                                                selectedModel === m && "bg-accent/50 font-medium"
                                                                            )}
                                                                        >
                                                                            <span className="flex-1">{m}</span>
                                                                            {selectedModel === m && <CheckCircle2 className="h-3.5 w-3.5 text-primary" />}
                                                                        </button>
                                                                    ))}
                                                                    {filteredModels.length === 0 && (
                                                                        <p className="px-3 py-4 text-sm text-muted-foreground text-center">No models match</p>
                                                                    )}
                                                                </div>
                                                                {currentProviderHasKey && (
                                                                    <div className="border-t border-border">
                                                                        {!showCustomModel ? (
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => { setShowCustomModel(true); setVerifyResult(null); setCustomModelInput(""); }}
                                                                                className="w-full px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:bg-accent text-left transition-colors"
                                                                            >
                                                                                Enter custom model ID →
                                                                            </button>
                                                                        ) : (
                                                                            <div className="p-3 space-y-2">
                                                                                <div className="flex gap-2">
                                                                                    <input
                                                                                        type="text"
                                                                                        placeholder="e.g. claude-opus-4-5"
                                                                                        value={customModelInput}
                                                                                        onChange={e => { setCustomModelInput(e.target.value); setVerifyResult(null); }}
                                                                                        onKeyDown={e => { if (e.key === "Enter") handleVerifyAndUseModel(); }}
                                                                                        autoFocus
                                                                                        className="flex-1 rounded-lg border border-input bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                                                                                    />
                                                                                    <Button type="button" size="sm" variant="outline" disabled={verifying || !customModelInput.trim()} onClick={handleVerifyAndUseModel}>
                                                                                        {verifying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Verify"}
                                                                                    </Button>
                                                                                    <button type="button" onClick={() => { setShowCustomModel(false); setCustomModelInput(""); setVerifyResult(null); }} className="rounded-lg border border-border bg-background p-1.5 text-muted-foreground hover:bg-accent transition-colors">
                                                                                        <X className="h-3.5 w-3.5" />
                                                                                    </button>
                                                                                </div>
                                                                                {verifyResult && (
                                                                                    <p className={cn("text-xs flex items-center gap-1.5", verifyResult.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive")}>
                                                                                        {verifyResult.ok ? <><CheckCircle2 className="h-3.5 w-3.5" /> Model verified!</> : <><X className="h-3.5 w-3.5" /> {verifyResult.reason}</>}
                                                                                    </p>
                                                                                )}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            )}

                                            {/* API Key */}
                                            <div className="space-y-2">
                                                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">API Key</p>
                                                {currentProviderHasKey && !editingKey && (
                                                    <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/30 px-3 py-2.5">
                                                        <div className="flex h-6 w-6 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-900/50">
                                                            <KeyRound className="h-3 w-3 sm:h-4 sm:w-4 text-emerald-600 dark:text-emerald-400" />
                                                        </div>
                                                        <div className="flex-1 min-w-0">
                                                            <p className="text-xs sm:text-sm font-medium text-emerald-700 dark:text-emerald-400">Key saved</p>
                                                            <p className="text-[10px] sm:text-xs text-muted-foreground font-mono">••••••••••••••</p>
                                                        </div>
                                                        <button type="button" onClick={() => { setEditingKey(true); setApiKey(""); }} className="shrink-0 flex items-center gap-1 rounded-lg border border-border bg-background px-2 py-1 text-[10px] sm:text-xs font-medium text-foreground hover:bg-accent transition-colors">
                                                            <Pencil className="h-2.5 w-2.5" /> Update
                                                        </button>
                                                        {!confirmDelete ? (
                                                            <button type="button" onClick={() => setConfirmDelete(true)} className="shrink-0 flex items-center justify-center rounded-lg border border-border bg-background p-1 text-muted-foreground hover:text-destructive hover:border-destructive/50 hover:bg-destructive/5 transition-colors">
                                                                <Trash2 className="h-3 w-3" />
                                                            </button>
                                                        ) : (
                                                            <div className="shrink-0 flex items-center gap-1">
                                                                <button type="button" onClick={handleRemoveKey} disabled={removing} className="flex items-center gap-1 rounded-lg bg-destructive px-2 py-1 text-[10px] sm:text-xs font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors">
                                                                    {removing ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Trash2 className="h-2.5 w-2.5" />} Del
                                                                </button>
                                                                <button type="button" onClick={() => setConfirmDelete(false)} className="rounded-lg border border-border bg-background p-1 text-muted-foreground hover:bg-accent transition-colors">
                                                                    <X className="h-2.5 w-2.5" />
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}
                                                {showKeyInput && (
                                                    <div className="space-y-2">
                                                        {editingKey && (
                                                            <div className="flex items-center justify-between">
                                                                <p className="text-xs text-muted-foreground">Paste your new key below</p>
                                                                <button type="button" onClick={() => { setEditingKey(false); setApiKey(""); }} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors">
                                                                    <X className="h-3 w-3" /> Cancel
                                                                </button>
                                                            </div>
                                                        )}
                                                        <div className="relative">
                                                            <Input
                                                                type={showKey ? "text" : "password"}
                                                                placeholder="Paste your API key here…"
                                                                value={apiKey}
                                                                onChange={(e) => setApiKey(e.target.value)}
                                                                className="pr-10 font-mono text-sm"
                                                                autoFocus={editingKey}
                                                                onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") { setEditingKey(false); setApiKey(""); } }}
                                                            />
                                                            <button type="button" onClick={() => setShowKey(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors">
                                                                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                                            </button>
                                                        </div>
                                                        <p className="text-xs text-muted-foreground">
                                                            Get your key from{" "}
                                                            <a href={PROVIDER_DOCS[selectedProvider] ?? "#"} target="_blank" rel="noreferrer" className="text-primary underline-offset-4 hover:underline font-medium">
                                                                {providerLabel(selectedProvider)} →
                                                            </a>
                                                        </p>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Save */}
                                            <Button onClick={handleSave} disabled={saving || (!currentProviderHasKey && !apiKey.trim()) || (editingKey && !apiKey.trim())} className="w-full">
                                                {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</> : editingKey ? "Update Key" : currentProviderHasKey ? "Save Model" : "Save Key & Model"}
                                            </Button>
                                        </>
                                    )}
                                </div>
                            )}

                            {/* ── Account tab ── */}
                            {activeTab === "account" && (
                                <div className="px-3 sm:px-8 py-4 sm:py-7 space-y-4 sm:space-y-6">
                                    <div>
                                        <h2 className="text-sm sm:text-base font-semibold">Account</h2>
                                        <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">Manage your profile and preferences.</p>
                                    </div>

                                    {/* User info */}
                                    <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 px-3 sm:px-5 py-3 sm:py-4">
                                        <div className="flex h-9 w-9 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                                            <UserCircle className="h-5 w-5 sm:h-7 sm:w-7" />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-semibold truncate">{user.name}</p>
                                            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                                        </div>
                                    </div>

                                    {/* Appearance */}
                                    <div className="flex items-center justify-between rounded-xl border border-border bg-background px-3 sm:px-5 py-3 sm:py-3.5">
                                        <div>
                                            <p className="text-sm font-medium">Appearance</p>
                                            <p className="text-xs text-muted-foreground mt-0.5">Toggle light / dark mode</p>
                                        </div>
                                        <ThemeToggle />
                                    </div>

                                    {/* Logout */}
                                    <div className="pt-2 border-t border-border">
                                        <Button variant="outline" className="w-full text-destructive hover:text-destructive hover:bg-destructive/5 hover:border-destructive/40" onClick={handleLogout}>
                                            <LogOutIcon className="h-4 w-4 mr-2" /> Log out
                                        </Button>
                                    </div>
                                </div>
                            )}

                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </>
    );
}
