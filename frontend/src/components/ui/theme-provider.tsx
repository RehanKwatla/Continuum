import * as React from "react";

const THEME_STORAGE_KEY = "continuum.theme";

export type Theme = "light" | "dark" | "system";

export interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: "light" | "dark";
  isDark: boolean;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const DEFAULT_THEME_VALUE: ThemeContextValue = {
  theme: "dark",
  resolvedTheme: "dark",
  isDark: true,
  setTheme: () => {},
  toggleTheme: () => {},
};

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const context = React.useContext(ThemeContext);
  if (!context) return DEFAULT_THEME_VALUE;
  return context;
}

export function ThemeProvider({
  children,
  defaultTheme = "dark",
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
      const isDark = effective === "dark";
      document.documentElement.classList.toggle("dark", isDark);
      document.documentElement.classList.toggle("light", !isDark);
    };
    resolve();
    media.addEventListener("change", resolve);
    return () => media.removeEventListener("change", resolve);
  }, [storedTheme]);

  // Apply resolved theme whenever it changes.
  React.useEffect(() => {
    if (typeof document === "undefined") return;
    const isDark = resolvedTheme === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    document.documentElement.classList.toggle("light", !isDark);
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
    const next: Theme = resolvedTheme === "dark" ? "light" : "dark";
    setStoredTheme(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* localStorage unavailable */
    }
  }, [resolvedTheme]);

  return (
    <ThemeContext.Provider
      value={{
        theme: storedTheme,
        resolvedTheme,
        isDark: resolvedTheme === "dark",
        setTheme,
        toggleTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}
