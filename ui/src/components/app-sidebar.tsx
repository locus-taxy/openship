import { BookOpen, UserPlus, Sparkles, BarChart2 } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { NavUser } from "@/components/nav-user";
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarHeader,
    SidebarRail,
    SidebarGroup,
    SidebarGroupLabel,
    SidebarMenu,
    SidebarMenuItem,
    SidebarMenuButton,
} from "@/components/ui/sidebar";

const NAV_ITEMS = [
    { title: "Dashboard", icon: BarChart2, url: "/analytics" },
    { title: "Enroll", icon: UserPlus, url: "/enroll" },
    { title: "Syllabi", icon: BookOpen, url: "/syllabi" },
]

export function AppSidebar() {
    const navigate = useNavigate();
    const { pathname } = useLocation();

    return (
        <Sidebar>
            <SidebarHeader>
                <div className="flex items-center gap-2 px-2 py-1">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600">
                        <Sparkles className="h-4 w-4 text-white" />
                    </div>
                    <span className="text-xl font-bold bg-gradient-to-r from-violet-500 to-indigo-500 bg-clip-text text-transparent">
                        Openship
                    </span>
                </div>
            </SidebarHeader>
            <SidebarContent>
                <SidebarGroup>
                    <SidebarGroupLabel>Menu</SidebarGroupLabel>
                    <SidebarMenu>
                        {NAV_ITEMS.map(({ title, icon: Icon, url }) => {
                            const isActive = pathname === url || pathname.startsWith(url + "/")
                            return (
                                <SidebarMenuItem key={title}>
                                    <SidebarMenuButton
                                        isActive={isActive}
                                        onClick={() => navigate(url)}
                                        tooltip={title}
                                    >
                                        <Icon />
                                        <span>{title}</span>
                                    </SidebarMenuButton>
                                </SidebarMenuItem>
                            )
                        })}
                    </SidebarMenu>
                </SidebarGroup>
            </SidebarContent>
            <SidebarFooter>
                <NavUser />
            </SidebarFooter>
            <SidebarRail />
        </Sidebar>
    );
}
