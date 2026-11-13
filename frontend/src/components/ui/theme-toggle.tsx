import * as React from "react";
import { Moon, Sun } from "lucide-react";

import { useTheme } from "@/components/ui/theme-provider";
import { Tooltip } from "@/components/common/Tooltip";
import { cn } from "@/lib/utils";

export interface ThemeToggleProps {
  className?: string;
  showLabel?: boolean;
  size?: "sm" | "default";
}

/**
 * Toggle switch in the UI / UX to change the theme between Dark and Light.
 * Supports smooth sliding animations, Sun/Moon icons, and keyboard accessibility.
 */
export function ThemeToggle({
  className,
  showLabel = false,
  size = "default",
}: ThemeToggleProps) {
  const { resolvedTheme, toggleTheme, isDark } = useTheme();
  const isSmall = size === "sm";

  return (
    <Tooltip label={isDark ? "Switch to light mode" : "Switch to dark mode"}>
      <div className={cn("inline-flex items-center gap-2", className)}>
        {showLabel ? (
          <span className="text-xs font-medium text-muted-foreground select-none">
            {isDark ? "Dark theme" : "Light theme"}
          </span>
        ) : null}

        <button
          type="button"
          role="switch"
          aria-checked={isDark}
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          onClick={toggleTheme}
          className={cn(
            "relative inline-flex shrink-0 cursor-pointer rounded-full border border-border bg-secondary/80 p-0.5 transition-colors duration-200 ease-in-out hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background active:scale-95",
            isSmall ? "h-6 w-11" : "h-7 w-14",
          )}
        >
          {/* Background icons in the track */}
          <span className="absolute inset-0 flex items-center justify-between px-1.5 pointer-events-none select-none">
            <Sun
              className={cn(
                "transition-opacity duration-200",
                isSmall ? "h-3 w-3" : "h-3.5 w-3.5",
                isDark ? "opacity-30 text-muted-foreground" : "opacity-100 text-amber-500",
              )}
            />
            <Moon
              className={cn(
                "transition-opacity duration-200",
                isSmall ? "h-3 w-3" : "h-3.5 w-3.5",
                isDark ? "opacity-100 text-orchid" : "opacity-30 text-muted-foreground",
              )}
            />
          </span>

          {/* Sliding knob (thumb) */}
          <span
            className={cn(
              "pointer-events-none flex items-center justify-center rounded-full bg-card shadow-md border border-border/80 transition-transform duration-200 ease-out",
              isSmall ? "h-4.5 w-4.5" : "h-5.5 w-5.5",
              isDark
                ? isSmall
                  ? "translate-x-5 text-orchid"
                  : "translate-x-7 text-orchid"
                : "translate-x-0 text-amber-500",
            )}
          >
            {isDark ? (
              <Moon className={cn(isSmall ? "h-2.5 w-2.5" : "h-3 w-3", "fill-orchid/20")} />
            ) : (
              <Sun className={cn(isSmall ? "h-2.5 w-2.5" : "h-3 w-3", "fill-amber-500/20")} />
            )}
          </span>
        </button>
      </div>
    </Tooltip>
  );
}
