import { Outlet } from "react-router"
import { AppSidebar } from "@/components/app-sidebar"
import { Toaster } from "@/components/ui/toaster"
import {
    SidebarInset,
    SidebarProvider,
} from "@/components/ui/sidebar"
import PluginHeader from "../partials/pluginHeader"
import PluginInfo from "../partials/pluginInfo"
import { useEffect } from "react"
import useStore from "../../store"
import axios from "axios"

export default function Layout() {

    const { setIsCredentialsDialog, setCredentialsNotPresent } = useStore((state: any) => state);

    const checkForTokenExpiry = async (token: any) => {
        try {

            if (!token) {
                return true;
            }

            const response: any = await axios.get("/auth/check-token-expiry", { params: { token } });
            return response.data.is_token_expired;
        } catch (error) {
            console.log(error);
            return true;
        }
    }

    const clearAllCookies = () => {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookieName = cookies[i].split('=')[0].trim();
            document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
        }
    }

    const checkForCredentials = () => {
        const cookies = document.cookie.split(';');

        let isCredentialsExisit = false;

        cookies.forEach(async (cookie) => {
            const [key, value] = cookie.split('=');

            if (key === 'token') {
                isCredentialsExisit = true;

                // const isTokenExpired = await checkForTokenExpiry(value);
                const isTokenExpired = false;

                if (isTokenExpired) {
                    clearAllCookies();
                    setCredentialsNotPresent(true);
                    setIsCredentialsDialog(true);
                } else {
                    setCredentialsNotPresent(false);
                }
            } else {
                clearAllCookies();
                setIsCredentialsDialog(true);
                setCredentialsNotPresent(true);
            }
        });


        if (!isCredentialsExisit) {
            setIsCredentialsDialog(true);
        }
    }

    useEffect(() => {
        checkForCredentials();
    }, []);

    return (
        <SidebarProvider>
            <AppSidebar />
            <SidebarInset>
                <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
                    <main>
                        <div className="grid auto-rows-min gap-4 md:grid-cols-3">
                            <div className="h-screen col-span-2">
                                <PluginHeader />
                                <Outlet />
                            </div>
                            <div className="bg-muted/50 col-span-1 overflow-y-auto p-4 mt-4 rounded-2xl h-9/10">
                                <PluginInfo />
                            </div>
                        </div>
                    </main>
                    <Toaster />
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
