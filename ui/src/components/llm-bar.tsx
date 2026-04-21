/**
 * LlmBar — compact provider + model selector shown at the top of generation pages.
 * Reads current settings and lets the user switch inline without opening the full Settings dialog.
 */
import { useState, useEffect, useRef } from "react";
import { Settings, ChevronDown, CheckCircle2, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { getRequest, putRequest, postRequest } from "@/services";
import useStore from "@/store";

interface Provider { value: string; label: string }

interface SettingsData {
    llm_provider: string | null;
    llm_model: string | null;
    provider_keys: Record<string, boolean>;
    supported_providers: Provider[];
    provider_models: Record<string, string[]>;
}

export function LlmBar() {
    const { setSettingsOpen, settingsOpen, setPendingProvider } = useStore((s: any) => s);
    const [data, setData] = useState<SettingsData | null>(null);
    const [liveModels, setLiveModels] = useState<string[]>([]);
    const [providerOpen, setProviderOpen] = useState(false);
    const [modelOpen, setModelOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [modelSearch, setModelSearch] = useState("");
    const [customModelInput, setCustomModelInput] = useState("");
    const [showCustomModel, setShowCustomModel] = useState(false);
    const [verifying, setVerifying] = useState(false);
    const [verifyResult, setVerifyResult] = useState<{ ok: boolean; reason?: string } | null>(null);
    const ref = useRef<HTMLDivElement>(null);

    async function load() {
        const { success, data: d } = await getRequest("/py/auth/me/settings");
        if (success) {
            setData(d);
            // Fetch live models for current provider
            if (d.llm_provider && d.provider_keys?.[d.llm_provider]) {
                const { success: ms, data: md } = await getRequest(`/py/auth/me/models?provider=${d.llm_provider}`);
                if (ms && md.models?.length) setLiveModels(md.models);
            }
        }
    }

    useEffect(() => { load(); }, []);

    // Reload whenever the settings modal closes so the bar reflects saved changes
    useEffect(() => { if (!settingsOpen) load(); }, [settingsOpen]);

    // Close dropdowns on outside click
    useEffect(() => {
        function handler(e: MouseEvent) {
            if (ref.current && !ref.current.contains(e.target as Node)) {
                setProviderOpen(false);
                setModelOpen(false);
            }
        }
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    async function switchProvider(p: string) {
        setProviderOpen(false);
        if (!data) return;
        if (!data.provider_keys[p]) {
            setPendingProvider(p);
            setSettingsOpen(true);
            return;
        }
        setSaving(true);
        setModelSearch("");
        setShowCustomModel(false);
        setCustomModelInput("");
        setVerifyResult(null);
        const { success: ms, data: md } = await getRequest(`/py/auth/me/models?provider=${p}`);
        const models = (ms && md.models?.length) ? md.models : (data.provider_models[p] ?? []);
        setLiveModels(models);
        await putRequest("/py/auth/me/settings", {
            llm_provider: p,
            llm_model: models[0] ?? null,
        });
        await load();
        setSaving(false);
    }

    async function switchModel(m: string) {
        setModelOpen(false);
        setModelSearch("");
        setShowCustomModel(false);
        setCustomModelInput("");
        setVerifyResult(null);
        if (!data?.llm_provider) return;
        setSaving(true);
        await putRequest("/py/auth/me/settings", {
            llm_provider: data.llm_provider,
            llm_model: m,
        });
        await load();
        setSaving(false);
    }

    async function handleVerifyCustomModel() {
        const m = customModelInput.trim();
        if (!m || !llm_provider) return;
        setVerifying(true);
        setVerifyResult(null);
        const { success, data: rd } = await postRequest(
            `/py/auth/me/models/verify?provider=${llm_provider}&model=${encodeURIComponent(m)}`, {}
        );
        setVerifying(false);
        if (!success) { setVerifyResult({ ok: false, reason: "Verification request failed." }); return; }
        if (rd.ok) {
            await switchModel(m);
            setShowCustomModel(false);
            setCustomModelInput("");
            setVerifyResult(null);
        } else {
            setVerifyResult({ ok: false, reason: rd.reason });
        }
    }

    if (!data) return null;

    const { llm_provider, llm_model, supported_providers, provider_models, provider_keys } = data;
    const hasProvider = llm_provider && provider_keys[llm_provider];
    const providerLabel = supported_providers.find(p => p.value === llm_provider)?.label ?? llm_provider ?? "No provider";
    // Prefer live-fetched models, fall back to static list
    const availableModels = liveModels.length > 0 ? liveModels : (provider_models[llm_provider ?? ""] ?? []);
    const filteredModels = modelSearch
        ? availableModels.filter(m => m.toLowerCase().includes(modelSearch.toLowerCase()))
        : availableModels;

    return (
        <div ref={ref} className="flex items-center gap-2 flex-wrap">
            {/* Provider pill */}
            <div className="relative">
                <button
                    type="button"
                    onClick={() => { setProviderOpen(o => !o); setModelOpen(false); }}
                    className={cn(
                        "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors hover:bg-accent",
                        hasProvider
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400"
                            : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400"
                    )}
                >
                    {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className={cn("h-3 w-3", !hasProvider && "opacity-40")} />}
                    {hasProvider ? providerLabel : "Set provider"}
                    <ChevronDown className={cn("h-3 w-3 transition-transform", providerOpen && "rotate-180")} />
                </button>
                {providerOpen && (
                    <div className="absolute z-50 top-full mt-1 left-0 w-44 rounded-xl border border-border bg-popover shadow-lg overflow-hidden">
                        {supported_providers.map(p => (
                            <button
                                key={p.value}
                                type="button"
                                onClick={() => switchProvider(p.value)}
                                className={cn(
                                    "w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-accent transition-colors",
                                    llm_provider === p.value && "bg-accent/50 font-semibold"
                                )}
                            >
                                <span className="flex-1">{p.label}</span>
                                {provider_keys[p.value]
                                    ? <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                                    : <Settings className="h-3 w-3 text-muted-foreground opacity-50" />
                                }
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Model pill — only when provider is configured */}
            {hasProvider && availableModels.length > 0 && (
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => { setModelOpen(o => !o); setProviderOpen(false); setModelSearch(""); }}
                        className="flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-3 py-1 text-xs font-mono font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                    >
                        {llm_model || availableModels[0]}
                        <ChevronDown className={cn("h-3 w-3 transition-transform", modelOpen && "rotate-180")} />
                    </button>
                    {modelOpen && (
                        <div className="absolute z-50 top-full mt-1 left-0 w-64 rounded-xl border border-border bg-popover shadow-lg overflow-hidden">
                            {/* Search */}
                            <div className="p-2 border-b border-border">
                                <input
                                    type="text"
                                    placeholder="Search models…"
                                    value={modelSearch}
                                    onChange={e => setModelSearch(e.target.value)}
                                    onClick={e => e.stopPropagation()}
                                    autoFocus
                                    className="w-full rounded-lg border border-input bg-background px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
                                />
                            </div>
                            {/* Model list */}
                            <div className="max-h-24 overflow-y-auto">
                                {filteredModels.map(m => (
                                    <button
                                        key={m}
                                        type="button"
                                        onClick={() => switchModel(m)}
                                        className={cn(
                                            "w-full flex items-center gap-2 px-3 py-2 text-xs font-mono text-left hover:bg-accent transition-colors",
                                            (llm_model || availableModels[0]) === m && "bg-accent/50 font-semibold"
                                        )}
                                    >
                                        <span className="flex-1">{m}</span>
                                        {(llm_model || availableModels[0]) === m && <CheckCircle2 className="h-3 w-3 text-primary" />}
                                    </button>
                                ))}
                                {filteredModels.length === 0 && (
                                    <p className="px-3 py-3 text-xs text-muted-foreground text-center">No models match</p>
                                )}
                            </div>
                            {/* Custom model */}
                            {provider_keys[llm_provider ?? ""] && (
                                <div className="border-t border-border">
                                    {!showCustomModel ? (
                                        <button
                                            type="button"
                                            onClick={() => { setShowCustomModel(true); setVerifyResult(null); setCustomModelInput(""); }}
                                            className="w-full px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-accent text-left transition-colors"
                                        >
                                            Enter custom model ID →
                                        </button>
                                    ) : (
                                        <div className="p-2 space-y-1.5">
                                            <div className="flex gap-1">
                                                <input
                                                    type="text"
                                                    placeholder="e.g. claude-opus-4-5"
                                                    value={customModelInput}
                                                    onChange={e => { setCustomModelInput(e.target.value); setVerifyResult(null); }}
                                                    onKeyDown={e => { if (e.key === "Enter") handleVerifyCustomModel(); }}
                                                    autoFocus
                                                    className="flex-1 rounded-lg border border-input bg-background px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ring"
                                                />
                                                <button
                                                    type="button"
                                                    disabled={verifying || !customModelInput.trim()}
                                                    onClick={handleVerifyCustomModel}
                                                    className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs font-medium hover:bg-accent disabled:opacity-50 transition-colors"
                                                >
                                                    {verifying ? <Loader2 className="h-3 w-3 animate-spin" /> : "Verify"}
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => { setShowCustomModel(false); setCustomModelInput(""); setVerifyResult(null); }}
                                                    className="rounded-lg border border-border bg-background p-1.5 text-muted-foreground hover:bg-accent transition-colors"
                                                >
                                                    <X className="h-3 w-3" />
                                                </button>
                                            </div>
                                            {verifyResult && (
                                                <p className={cn("text-xs flex items-center gap-1", verifyResult.ok ? "text-emerald-600" : "text-destructive")}>
                                                    {verifyResult.ok ? <CheckCircle2 className="h-3 w-3" /> : <X className="h-3 w-3" />}
                                                    {verifyResult.ok ? "Verified & applied!" : verifyResult.reason}
                                                </p>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* No key for provider → link to settings */}
            {llm_provider && !provider_keys[llm_provider] && (
                <button
                    type="button"
                    onClick={() => setSettingsOpen(true)}
                    className="text-xs text-amber-600 dark:text-amber-400 underline-offset-4 hover:underline"
                >
                    Add API key →
                </button>
            )}
        </div>
    );
}
