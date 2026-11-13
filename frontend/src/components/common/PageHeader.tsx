import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1.5">
          {eyebrow ? <p className="label-eyebrow">{eyebrow}</p> : null}
          <h1 className="font-display text-3xl font-bold tracking-tight text-foreground sm:text-[2rem] sm:leading-tight">
            {title}
          </h1>
          {description ? (
            <div className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {description}
            </div>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2.5">{actions}</div> : null}
      </div>
    </div>
  );
}

export function MetricTile({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="border-b border-border p-5 sm:border-b-0 sm:border-r sm:last:border-r-0 transition-colors hover:bg-card/80">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-primary">{label}</p>
        {icon ? <span className="text-muted-foreground/80">{icon}</span> : null}
      </div>
      <p className="mt-3 font-display text-3xl font-bold tabular-nums tracking-tight text-foreground">
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/** Generic placeholder block used while a page's primary query is loading. */
export function PanelSkeleton({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={className}>
      <Skeleton className="h-24 w-full rounded-lg" />
      <div className="mt-3 space-y-2">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} className="h-10 w-full rounded-md" />
        ))}
      </div>
    </div>
  );
}

export function TableSkeleton({
  columns,
  rows = 5,
}: {
  columns: string[];
  rows?: number;
}) {
  return (
    <div className="panel overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => (
              <TableHead key={column}>{column}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <TableRow key={rowIndex} className="hover:bg-transparent">
              {columns.map((column) => (
                <TableCell key={column}>
                  <Skeleton className="h-4 w-full max-w-[180px]" />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
