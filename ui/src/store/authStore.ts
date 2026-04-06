import { create } from "zustand";
import axios from "axios";

interface UserInfo {
    id: number;
    email: string;
    name: string;
    is_active: boolean;
}

interface AuthState {
    user: UserInfo | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    initialized: boolean;
    sessionExpired: boolean;

    signup: (name: string, email: string, password: string) => Promise<void>;
    login: (email: string, password: string) => Promise<void>;
    logout: (reason?: "session_expired") => void;
    initAuth: () => Promise<void>;
    refreshAccessToken: () => Promise<void>;
    clearSessionExpired: () => void;
}

const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    initialized: false,
    sessionExpired: false,

    signup: async (name, email, password) => {
        await axios.post("/py/auth/signup", { name, email, password });
    },

    login: async (email, password) => {
        const res = await axios.post("/py/auth/login", { email, password });
        set({ user: res.data.user, isAuthenticated: true });
    },

    logout: (reason?) => {
        set({
            user: null,
            isAuthenticated: false,
            sessionExpired: reason === "session_expired",
        });
        axios.post("/py/auth/logout").catch(() => {});
    },

    clearSessionExpired: () => set({ sessionExpired: false }),

    refreshAccessToken: async () => {
        await axios.post("/py/auth/refresh");
    },

    initAuth: async () => {
        if (get().initialized || get().isLoading) return;
        set({ isLoading: true });
        try {
            await axios.post("/py/auth/refresh");
            const userRes = await axios.get("/py/auth/me");
            set({
                user: userRes.data,
                isAuthenticated: true,
                isLoading: false,
                initialized: true,
            });
        } catch {
            set({
                user: null,
                isAuthenticated: false,
                isLoading: false,
                initialized: true,
            });
        }
    },
}));

export default useAuthStore;
