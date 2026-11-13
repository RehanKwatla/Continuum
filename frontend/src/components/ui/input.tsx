import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-lg border border-border bg-card/60 px-3 py-1.5 text-sm text-foreground transition-all",
        "placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/40",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
