import { BookOpen, UserPlus, Sparkles, BarChart2, GraduationCap } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { NavUser } from "@/components/nav-user";
import { cn } from "@/lib/utils";
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarHeader,
    SidebarRail,
    SidebarGroup,
    SidebarGroupLabel,
} from "@/components/ui/sidebar";

const NAV_ITEMS = [
    { title: "Dashboard", icon: BarChart2, url: "/analytics" },
    { title: "Enroll", icon: UserPlus, url: "/enroll" },
    { title: "Courses", icon: BookOpen, url: "/syllabi" },
    { title: "Onboarding", icon: GraduationCap, url: "/onboarding" },
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
                <SidebarGroup className="px-4 py-2">
                    <SidebarGroupLabel className="px-1 mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
                        Menu
                    </SidebarGroupLabel>
                    <div className="flex flex-col gap-1.5">
                        {NAV_ITEMS.map(({ title, icon: Icon, url }) => {
                            const isActive = pathname === url || pathname.startsWith(url + "/")
                            return (
                                <button
                                    key={title}
                                    onClick={() => navigate(url)}
                                    className={cn(
                                        "group flex items-center gap-3 rounded-xl px-4 py-3.5 text-sm font-medium transition-all duration-150 w-full text-left",
                                        isActive
                                            ? "bg-primary/10 text-primary font-semibold"
                                            : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                    )}
                                >
                                    <Icon className={cn(
                                        "h-4 w-4 shrink-0 transition-colors",
                                        isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                                    )} />
                                    <span>{title}</span>
                                </button>
                            )
                        })}
                    </div>
                </SidebarGroup>
            </SidebarContent>
            <SidebarFooter>
                <NavUser />
            </SidebarFooter>
            <SidebarRail />
        </Sidebar>
    );
}
