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
    accessToken: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    initialized: boolean;

    signup: (name: string, email: string, password: string) => Promise<void>;
    login: (email: string, password: string) => Promise<void>;
    logout: () => void;
    initAuth: () => Promise<void>;
    refreshAccessToken: () => Promise<string>;
}

const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    accessToken: null,
    isAuthenticated: false,
    isLoading: false,
    initialized: false,

    signup: async (name, email, password) => {
        await axios.post("/py/auth/signup", { name, email, password });
    },

    login: async (email, password) => {
        const res = await axios.post("/py/auth/login", { email, password });
        const { user, access_token } = res.data;
        set({ user, accessToken: access_token, isAuthenticated: true });
    },

    logout: () => {
        set({ user: null, accessToken: null, isAuthenticated: false });
        axios.post("/py/auth/logout").catch(() => {});
    },

    refreshAccessToken: async () => {
        const res = await axios.post("/py/auth/refresh");
        const accessToken = res.data.access_token;
        set({ accessToken });
        return accessToken;
    },

    initAuth: async () => {
        if (get().initialized || get().isLoading) return;
        set({ isLoading: true });
        try {
            const tokenRes = await axios.post("/py/auth/refresh");
            const accessToken = tokenRes.data.access_token;

            const userRes = await axios.get("/py/auth/me", {
                headers: { Authorization: `Bearer ${accessToken}` },
            });

            set({
                accessToken,
                user: userRes.data,
                isAuthenticated: true,
                isLoading: false,
                initialized: true,
            });
        } catch {
            set({
                user: null,
                accessToken: null,
                isAuthenticated: false,
                isLoading: false,
                initialized: true,
            });
        }
    },
}));

export default useAuthStore;
