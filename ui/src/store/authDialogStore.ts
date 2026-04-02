import { create } from "zustand";

type AuthDialogView = "login" | "signup";

interface AuthDialogState {
    isOpen: boolean;
    view: AuthDialogView;
    openLogin: () => void;
    openSignup: () => void;
    close: () => void;
    switchView: (view: AuthDialogView) => void;
}

const useAuthDialogStore = create<AuthDialogState>((set) => ({
    isOpen: false,
    view: "login",
    openLogin: () => set({ isOpen: true, view: "login" }),
    openSignup: () => set({ isOpen: true, view: "signup" }),
    close: () => set({ isOpen: false }),
    switchView: (view) => set({ view }),
}));

export default useAuthDialogStore;
