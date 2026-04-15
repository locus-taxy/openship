import { create } from "zustand";

const useStore = create((set) => ({
    pluginName: "",
    setPluginName: (pluginName: string) => set({ pluginName: pluginName }),
    hideHeader: false,
    setHideHeader: (hideHeader: boolean) => set({ hideHeader }),
}));

export default useStore;