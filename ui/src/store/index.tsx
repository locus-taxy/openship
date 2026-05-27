import { create } from "zustand"

const useStore = create((set) => ({
    pluginName: "",
    setPluginName: (pluginName: string) => set({ pluginName }),
    hideHeader: false,
    setHideHeader: (hideHeader: boolean) => set({ hideHeader }),
    settingsOpen: false,
    setSettingsOpen: (settingsOpen: boolean) => set({ settingsOpen }),
    pendingProvider: null as string | null,
    setPendingProvider: (pendingProvider: string | null) => set({ pendingProvider }),

    // Tracks in-progress syllabus generations across page navigations.
    // In-memory only — resets on browser refresh (which also kills the request).
    generatingSkills: {} as Record<number, boolean>,
    addGeneratingSkill: (skillId: number) =>
        set((s: any) => ({ generatingSkills: { ...s.generatingSkills, [skillId]: true } })),
    removeGeneratingSkill: (skillId: number) =>
        set((s: any) => {
            const next = { ...s.generatingSkills }
            delete next[skillId]
            return { generatingSkills: next }
        }),
}))

export default useStore
