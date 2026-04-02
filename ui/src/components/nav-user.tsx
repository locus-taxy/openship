import { SidebarMenu, SidebarMenuItem } from "@/components/ui/sidebar";
import { Button } from "./ui/button";
import { LogOutIcon, LogInIcon, UserPlus, UserCircle } from "lucide-react";
import useAuthStore from "@/store/authStore";
import useAuthDialogStore from "@/store/authDialogStore";

export function NavUser() {
    const { user, isAuthenticated, logout } = useAuthStore();
    const { openLogin, openSignup } = useAuthDialogStore();

    if (!isAuthenticated || !user) {
        return (
            <SidebarMenu>
                <SidebarMenuItem>
                    <div className="flex flex-col gap-2 px-1">
                        <Button variant="default" className="w-full" onClick={openLogin}>
                            <LogInIcon className="w-4 h-4 mr-2" />
                            Login
                        </Button>
                        <Button variant="outline" className="w-full" onClick={openSignup}>
                            <UserPlus className="w-4 h-4 mr-2" />
                            Sign up
                        </Button>
                    </div>
                </SidebarMenuItem>
            </SidebarMenu>
        );
    }

    return (
        <SidebarMenu>
            <SidebarMenuItem>
                <div className="flex items-center gap-2 px-2 py-2">
                    <UserCircle className="h-6 w-6 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{user.name}</p>
                        <p className="text-xs text-muted-foreground truncate">
                            {user.email}
                        </p>
                    </div>
                </div>
                <hr className="my-1" />
                <Button
                    variant="outline"
                    className="w-full mt-1"
                    onClick={logout}
                >
                    <LogOutIcon className="w-4 h-4 mr-2" />
                    Logout
                </Button>
            </SidebarMenuItem>
        </SidebarMenu>
    );
}
