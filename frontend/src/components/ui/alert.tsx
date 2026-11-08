import * as React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const alertVariants = cva("relative w-full rounded-lg border p-3 text-sm", {
  variants: {
    variant: {
      default: "border-border bg-card/60 text-foreground",
      info: "border-status-info/35 bg-status-info/[0.07] text-foreground",
      success: "border-status-ok/35 bg-status-ok/[0.07] text-foreground",
      warning: "border-status-warn/35 bg-status-warn/[0.07] text-foreground",
      destructive: "border-status-danger/40 bg-status-danger/[0.07] text-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

const ICONS = {
  default: Info,
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  destructive: AlertCircle,
} as const;

export interface AlertProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof alertVariants> {
  title?: string;
  icon?: boolean;
}

export function Alert({
  className,
  variant = "default",
  title,
  icon = true,
  children,
  ...props
}: AlertProps) {
  const Icon = ICONS[variant ?? "default"];
  return (
    <div role="alert" className={cn(alertVariants({ variant }), className)} {...props}>
      <div className="flex gap-3">
        {icon ? <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" /> : null}
        <div className="min-w-0 flex-1 space-y-1">
          {title ? <p className="text-sm font-medium leading-tight">{title}</p> : null}
          {children ? (
            <div className="text-xs leading-relaxed text-muted-foreground">{children}</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
