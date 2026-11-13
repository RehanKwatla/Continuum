"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/ui/theme-provider";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();

  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Theme
      </span>
      <div
        className="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border border-border bg-secondary items-center transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70 data-[state=checked]:bg-primary"
        onClick={toggleTheme}
        role="switch"
        aria-checked={resolvedTheme === "dark"}
        data-state={resolvedTheme}
      >
        <span
          className={cn(
            "pointer-events-none block h-4 w-4 rounded-full bg-card shadow-sm ring-0 transition-transform",
            resolvedTheme === "dark" ? "translate-x-5" : "translate-x-1",
          )}
        />
        <Sun className="absolute left-2.5 top-1 h-4 w-4 text-muted-foreground transition-opacity data-[state=unchecked]:opacity-100 data-[state=checked]:opacity-0" />
        <Moon className="absolute right-2.5 top-1 h-4 w-4 text-muted-foreground transition-opacity data-[state=checked]:opacity-100 data-[state=unchecked]:opacity-0" />
      </div>
      <Button
        variant="outline"
        size="icon"
        className="ml-1 hidden sm:block"
        onClick={() => setTheme("system")}
        aria-label="Use system theme"
        title="Use system theme"
        disabled={theme === "system"}
      >
        <span className="sr-only">Use system theme</span>
      </Button>
    </div>
  );
}
