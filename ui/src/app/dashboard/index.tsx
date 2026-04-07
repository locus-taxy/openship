import { Outlet, Navigate } from "react-router";
import { AppSidebar } from "@/components/app-sidebar";
import { Toaster } from "@/components/ui/toaster";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import PluginHeader from "../partials/pluginHeader";
import PluginInfo from "../partials/pluginInfo";
import { useEffect } from "react";
import useAuthStore from "@/store/authStore";
import { Loader2 } from "lucide-react";

export default function Layout() {
    const { initialized, isAuthenticated, initAuth } = useAuthStore();

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
    );
}
