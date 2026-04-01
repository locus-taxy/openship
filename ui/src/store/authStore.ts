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
    setAuth: (user: UserInfo, token: string, refreshToken: string) => void;
}

const useAuthStore = create<AuthState>((set, get) => ({
    user: null,
    accessToken: null,
    isAuthenticated: false,
    isLoading: false,
    initialized: false,

    setAuth: (user, token, refreshToken) => {
        localStorage.setItem("refresh_token", refreshToken);
        set({ user, accessToken: token, isAuthenticated: true, isLoading: false });
    },

    signup: async (name, email, password) => {
        await axios.post("/py/auth/signup", { name, email, password });
    },

    login: async (email, password) => {
        const res = await axios.post("/py/auth/login", { email, password });
        const { user, access_token, refresh_token } = res.data;
        get().setAuth(user, access_token, refresh_token);
    },

    logout: () => {
        localStorage.removeItem("refresh_token");
        set({ user: null, accessToken: null, isAuthenticated: false });
    },

    initAuth: async () => {
        const refresh = localStorage.getItem("refresh_token");
        if (!refresh) {
            set({ initialized: true });
            return;
        }
        set({ isLoading: true });
        try {
            const tokenRes = await axios.post("/py/auth/refresh", { refresh_token: refresh });
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
            localStorage.removeItem("refresh_token");
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
