import { create } from "zustand";

const useStore = create((set) => ({
    pluginName: "",
    setPluginName: (pluginName: string) => set({ pluginName: pluginName }),
}));

export default useStore;