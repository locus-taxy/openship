import axios from "axios";
import { toast } from "../hooks/use-toast";
import useAuthStore from "../store/authStore";

const api = axios.create();

api.interceptors.request.use((config) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

let isRefreshing = false;
let pendingRequests: Array<(token: string) => void> = [];

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            if (!isRefreshing) {
                isRefreshing = true;
                try {
                    await useAuthStore.getState().initAuth();
                    isRefreshing = false;

                    const newToken = useAuthStore.getState().accessToken;
                    if (newToken) {
                        pendingRequests.forEach((cb) => cb(newToken));
                        pendingRequests = [];
                        originalRequest.headers.Authorization = `Bearer ${newToken}`;
                        return api(originalRequest);
                    }
                } catch {
                    isRefreshing = false;
                }

                pendingRequests = [];
                useAuthStore.getState().logout();
                return Promise.reject(error);
            }

            return new Promise((resolve) => {
                pendingRequests.push((token: string) => {
                    originalRequest.headers.Authorization = `Bearer ${token}`;
                    resolve(api(originalRequest));
                });
            });
        }

        return Promise.reject(error);
    }
);

export const getRequest = async (url: string, params?: any) => {
    try {
        const response = await api.get(url, { params });
        return { success: true, data: response.data };
    } catch (error: any) {
        if (error?.response?.status !== 401) {
            console.error(error);
            toast({
                variant: "destructive",
                title: "Error",
                description: `${error?.response?.data?.detail || error?.response?.data?.message || "Something went wrong"}`,
            });
        }
        return { success: false, error };
    }
};

export const postRequest = async (url: string, data: any) => {
    try {
        const response = await api.post(url, data);
        return { success: true, data: response.data };
    } catch (error: any) {
        if (error?.response?.status !== 401) {
            console.error(error);
            toast({
                variant: "destructive",
                title: "Error",
                description: `${error?.response?.data?.detail || error?.response?.data?.message || "Something went wrong"}`,
            });
        }
        return { success: false, error };
    }
};

export default api;
