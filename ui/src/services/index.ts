import axios from "axios";
import { toast } from "../hooks/use-toast";
import useAuthStore from "../store/authStore";

const api = axios.create();

let isRefreshing = false;
let pendingRequests: Array<{
    resolve: () => void;
    reject: (error: unknown) => void;
}> = [];

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            if (!isRefreshing) {
                isRefreshing = true;
                try {
                    await useAuthStore.getState().refreshAccessToken();
                    isRefreshing = false;
                    pendingRequests.forEach((p) => p.resolve());
                    pendingRequests = [];
                    return api(originalRequest);
                } catch (refreshError) {
                    isRefreshing = false;
                    pendingRequests.forEach((p) => p.reject(refreshError));
                    pendingRequests = [];
                    useAuthStore.getState().logout("session_expired");
                    return Promise.reject(error);
                }
            }

            return new Promise((resolve, reject) => {
                pendingRequests.push({
                    resolve: () => resolve(api(originalRequest)),
                    reject,
                });
            });
        }

        return Promise.reject(error);
    }
);

/** FastAPI uses `detail`; validation errors use `detail` as an array. */
function formatApiError(error: unknown): string {
    const err = error as {
        response?: { data?: { detail?: unknown; message?: string } };
        message?: string;
    };
    const data = err?.response?.data;
    if (data?.detail !== undefined) {
        const d = data.detail;
        if (typeof d === "string") return d;
        if (Array.isArray(d))
            return d
                .map((item: { msg?: string; loc?: unknown }) =>
                    item?.msg ? item.msg : JSON.stringify(item),
                )
                .join("; ");
    }
    if (data?.message) return data.message;
    if (err?.message) return err.message;
    return String(error);
}

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
                description: formatApiError(error),
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
                description: formatApiError(error),
            });
        }
        return { success: false, error };
    }
};

export const putRequest = async (url: string, data: any) => {
    try {
        const response = await api.put(url, data);
        return { success: true, data: response.data };
    } catch (error: any) {
        if (error?.response?.status !== 401) {
            console.error(error);
            toast({
                variant: "destructive",
                title: "Error",
                description: formatApiError(error),
            });
        }
        return { success: false, error };
    }
};

export default api;
