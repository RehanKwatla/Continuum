import * as React from "react";

const THEME_STORAGE_KEY = "continuum.theme";

type Theme = "light" | "dark" | "system";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

export function useTheme() {
  const context = React.useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within a ThemeProvider");
  return context;
}

export function ThemeProvider({
  children,
  defaultTheme = "system",
}: {
  children: React.ReactNode;
  defaultTheme?: Theme;
}) {
  const [storedTheme, setStoredTheme] = React.useState<Theme>(defaultTheme);
  const [resolvedTheme, setResolvedTheme] = React.useState<"light" | "dark">("dark");

  // Read persisted preference on mount.
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (raw === "light" || raw === "dark" || raw === "system") {
        setStoredTheme(raw);
      }
    } catch {
      /* localStorage unavailable — fall back to default */
    }
  }, []);

  // Resolve the effective theme (system -> prefers-color-scheme).
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const resolve = () => {
      const effective = storedTheme === "system"
        ? (media.matches ? "dark" : "light")
        : storedTheme;
      setResolvedTheme(effective);
      document.documentElement.classList.toggle("dark", effective === "dark");
    };
    resolve();
    media.addEventListener("change", resolve);
    return () => media.removeEventListener("change", resolve);
  }, [storedTheme]);

  // Apply resolved theme whenever it changes.
  React.useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", resolvedTheme === "dark");
  }, [resolvedTheme]);

  const setTheme = React.useCallback(
    (next: Theme) => {
      setStoredTheme(next);
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        /* localStorage unavailable — preference won't persist across reloads */
      }
    },
    [],
  );

  const toggleTheme = React.useCallback(() => {
    setStoredTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  return (
    <ThemeContext.Provider value={{ theme: storedTheme, resolvedTheme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
