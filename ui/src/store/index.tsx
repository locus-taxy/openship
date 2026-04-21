import { create } from "zustand";

const useStore = create((set) => ({
    pluginName: "",
    setPluginName: (pluginName: string) => set({ pluginName: pluginName }),
    hideHeader: false,
    setHideHeader: (hideHeader: boolean) => set({ hideHeader }),
    settingsOpen: false,
    setSettingsOpen: (settingsOpen: boolean) => set({ settingsOpen }),
    pendingProvider: null as string | null,
    setPendingProvider: (pendingProvider: string | null) => set({ pendingProvider }),
}));

export default useStore;
