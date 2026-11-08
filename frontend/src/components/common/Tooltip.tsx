import * as React from "react";

import { cn } from "@/lib/utils";

/** Lightweight tooltip. Prefer this over a second component library. */
export function Tooltip({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("group/tip relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-[calc(100%+6px)] left-1/2 z-50 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 text-[11px] text-popover-foreground shadow-none group-hover/tip:block group-focus-within/tip:block"
      >
        {label}
      </span>
    </span>
  );
}
