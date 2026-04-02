import { useNavigate } from "react-router";
import { SidebarMenu, SidebarMenuItem } from "@/components/ui/sidebar";
import { Button } from "./ui/button";
import { LogOutIcon, UserCircle } from "lucide-react";
import useAuthStore from "@/store/authStore";

export function NavUser() {
    const { user, isAuthenticated, logout } = useAuthStore();
    const navigate = useNavigate();

    if (!isAuthenticated || !user) {
        return null;
    }

    function handleLogout() {
        logout();
        navigate("/login");
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
                    onClick={handleLogout}
                >
                    <LogOutIcon className="w-4 h-4 mr-2" />
                    Logout
                </Button>
            </SidebarMenuItem>
        </SidebarMenu>
    );
}
