import { Check, CircleAlert, CircleHelp, Scale, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/**
 * Design-ready specimens for later phases.
 * These are not wired to project data and must not be read as live verdicts.
 */
export function FutureWorkspacePreview() {
  return (
    <section className="space-y-4" aria-label="Future workspace preview">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="label-eyebrow">Prepared interface</p>
          <h2 className="mt-1 font-display text-xl font-medium text-sand">
            Claims, evidence and handover
          </h2>
        </div>
        <Badge variant="secondary">Not operational</Badge>
      </div>
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
        These controls are design specimens. Continuum does not extract claims, score evidence or
        generate a handover in this build. A claim can become Verified only after a human reviewer
        approves it.
      </p>

      <div className="grid gap-3 lg:grid-cols-2">
        <article className="panel p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-foreground">Sample claim</p>
            <Badge variant="ok">Verified</Badge>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            Refund retries are owned by the payments service, not the checkout client.
          </p>
          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            Evidence · commit a1c4 · issue #218 · p. 4
          </p>
        </article>

        <article className="panel space-y-3 p-4">
          <p className="label-eyebrow">Verdict vocabulary</p>
          <div className="flex flex-wrap gap-2">
            <Badge variant="ok">
              <ShieldCheck className="mr-1 h-3 w-3" />
              Verified
            </Badge>
            <Badge variant="info">Supported</Badge>
            <Badge variant="warn">
              <CircleHelp className="mr-1 h-3 w-3" />
              Uncertain
            </Badge>
            <Badge variant="danger">
              <CircleAlert className="mr-1 h-3 w-3" />
              Conflict
            </Badge>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-border pt-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Scale className="h-3.5 w-3.5" />
              Human approval required
            </div>
            <Button size="sm" disabled>
              <Check className="h-3.5 w-3.5" />
              Approve
            </Button>
          </div>
        </article>
      </div>

      <div className="panel p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium">Handover readiness</p>
          <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Unavailable
          </span>
        </div>
        <div className="mt-3 h-1 w-full bg-secondary">
          <div className="h-full w-0 bg-primary" />
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
          Readiness stays empty until sources are reconstructed and a reviewer accepts the
          resulting claims. No score is invented here.
        </p>
      </div>
    </section>
  );
}
