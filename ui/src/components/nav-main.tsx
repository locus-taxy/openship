"use client";

import { type LucideIcon } from "lucide-react";
import { SidebarGroup, SidebarGroupLabel } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

export function NavMain({
    items,
}: {
    items: {
        title: string;
        url: string;
        icon?: LucideIcon;
        isActive?: boolean;
    }[];
}) {
    return (
        <SidebarGroup className="px-4 py-2">
            <SidebarGroupLabel className="px-1 mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/60">
                Menu
            </SidebarGroupLabel>
            <div className="flex flex-col gap-1.5">
                {items.map((item) => (
                    <a
                        key={item.title}
                        href={item.url}
                        className={cn(
                            "group flex items-center gap-3 rounded-xl px-4 py-3.5 text-sm font-medium transition-all duration-150",
                            item.isActive
                                ? "bg-primary/10 text-primary font-semibold"
                                : "text-muted-foreground hover:bg-muted hover:text-foreground"
                        )}
                    >
                        {item.icon && (
                            <item.icon className={cn(
                                "h-4 w-4 shrink-0 transition-colors",
                                item.isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                            )} />
                        )}
                        <span>{item.title}</span>
                    </a>
                ))}
            </div>
        </SidebarGroup>
    );
}
