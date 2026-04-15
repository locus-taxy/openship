import { Outlet, Navigate } from "react-router";
import { AppSidebar } from "@/components/app-sidebar";
import { Toaster } from "@/components/ui/toaster";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import PluginHeader from "../partials/pluginHeader";
import { useEffect } from "react";
import useAuthStore from "@/store/authStore";
import useStore from "@/store";
import { Loader2 } from "lucide-react";

export default function Layout() {
    const { initialized, isAuthenticated, initAuth } = useAuthStore();
    const { hideHeader } = useStore((state: any) => state)

    useEffect(() => {
        initAuth();
    }, []);

    if (!initialized) {
        return (
            <div className="flex items-center justify-center h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return (
        <SidebarProvider>
            <AppSidebar />
            <SidebarInset>
                {!hideHeader && <PluginHeader />}
                <main className="flex-1 overflow-y-auto">
                    <Outlet />
                </main>
                <Toaster />
            </SidebarInset>
        </SidebarProvider>
    );
}
