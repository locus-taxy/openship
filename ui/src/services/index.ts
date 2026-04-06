import axios from "axios";
import { toast } from "../hooks/use-toast";

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
        const response = await axios.get(url, { params });
        return { success: true, data: response.data }
    } catch (error: any) {
        console.log(error);
        toast({
            variant: "destructive",
            title: "Error",
            description: formatApiError(error),
        })
        return { success: false, error };
    }
}

export const postRequest = async (url: string, data: any) => {
    try {
        const response = await axios.post(url, data);
        return { success: true, data: response.data }
    } catch (error: any) {
        console.log(error);
        toast({
            variant: "destructive",
            title: "Error",
            description: formatApiError(error),
        })
        return { success: false, error };
    }
}