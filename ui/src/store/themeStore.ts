import { create } from "zustand";

type Theme = "light" | "dark";

interface ThemeState {
    theme: Theme;
    setTheme: (theme: Theme) => void;
}

function applyTheme(theme: Theme) {
    const root = document.documentElement;
    if (theme === "dark") {
        root.classList.add("dark");
    } else {
        root.classList.remove("dark");
    }
}

const stored = (localStorage.getItem("theme") as Theme) || "dark";
applyTheme(stored);

const useThemeStore = create<ThemeState>((set) => ({
    theme: stored,
    setTheme: (theme) => {
        localStorage.setItem("theme", theme);
        applyTheme(theme);
        set({ theme });
    },
}));

export default useThemeStore;
