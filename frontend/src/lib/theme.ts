import { useCallback, useState } from "react";

export type Theme = "dark" | "light";
const STORAGE_KEY = "nexora.theme";

function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** Dark-first theme with a persisted preference (applied before paint in index.html). */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  const toggleTheme = useCallback(() => {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Preference simply is not persisted.
    }
    setTheme(next);
  }, []);

  return { theme, toggleTheme };
}
