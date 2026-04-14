// @ts-nocheck

import { BrainCircuit, BookOpen, UserPlus, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router";
import { NavMain } from "@/components/nav-main";
import { NavUser } from "@/components/nav-user";
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarHeader,
    SidebarRail,
} from "@/components/ui/sidebar";

// This is sample data.
const data = {
    user: {
        name: "shadcn",
        email: "m@example.com",
        avatar: "/avatars/shadcn.jpg",
    },
    teams: [
        {
            name: "NAME",
            logo: "",
            plan: "",
        },
    ],
    navMain: [
        {
            title: "Learning",
            url: "#",
            icon: BrainCircuit,
            isActive: true,
            items: [
                {
                    title: "Enroll",
                    icon: UserPlus,
                    url: "/enroll",
                    isActive: false,
                },
                {
                    title: "Syllabi",
                    icon: BookOpen,
                    url: "/syllabi",
                    isActive: false,
                },
            ],
        }
    ],
};

export function AppSidebar() {
    const navigate = useNavigate();
    const url = window.location.href;
    const currentPage = url.split("/").pop();

    function setActiveMenuItem(menus: any) {
        for (const menu of menus) {
            menu.isActive = false;
            for (const subMenu of menu.items) {
                if (subMenu.url === "/" + currentPage) {
                    subMenu.isActive = true;
                    menu.isActive = true;
                } else {
                    subMenu.isActive = false;
                }
            }
        }
    }

    useEffect(() => {
        setActiveMenuItem(data.navMain);
    }, [currentPage]);

    return (
        <Sidebar>
            <SidebarHeader>
                <button
                    onClick={() => navigate("/")}
                    className="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-sidebar-accent transition-colors w-full"
                >
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-indigo-600">
                        <Sparkles className="h-4 w-4 text-white" />
                    </div>
                    <span className="text-xl font-bold bg-gradient-to-r from-violet-500 to-indigo-500 bg-clip-text text-transparent">
                        Openship
                    </span>
                </button>
            </SidebarHeader>
            <SidebarContent>
                <NavMain items={data.navMain} />
            </SidebarContent>
            <SidebarFooter>
                <NavUser />
            </SidebarFooter>
            <SidebarRail />
        </Sidebar>
    );
}
