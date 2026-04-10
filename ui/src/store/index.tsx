import { create } from "zustand";

const useStore = create((set) => ({
    isCredentialsDialog: false,
    setIsCredentialsDialog: (isCredentialsDialog: boolean) => set({ isCredentialsDialog: isCredentialsDialog }),
    pluginName: "",
    setPluginName: (pluginName: string) => set({ pluginName: pluginName }),
    credentialsNotPresent: true,
    setCredentialsNotPresent: (credentialsNotPresent: boolean) => set({ credentialsNotPresent: credentialsNotPresent }),
}));

export default useStore;