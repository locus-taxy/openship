import { Sun, Moon } from "lucide-react";
import useThemeStore from "@/store/themeStore";
import { Button } from "@/components/ui/button";

export function ThemeToggle({ variant = "ghost" }: { variant?: "ghost" | "outline" }) {
    const { theme, setTheme } = useThemeStore();
    const isDark = theme === "dark";

    return (
        <Button
            variant={variant}
            size="icon"
            onClick={() => setTheme(isDark ? "light" : "dark")}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            className="h-8 w-8"
        >
            {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
    );
}
