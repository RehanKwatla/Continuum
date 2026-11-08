import { Link, useLocation } from "react-router-dom";
import { Compass, LayoutDashboard } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  const location = useLocation();

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="w-full max-w-md space-y-4 text-center">
        <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-border/80 bg-secondary/60 text-muted-foreground">
          <Compass className="h-4 w-4" />
        </span>
        <div className="space-y-1.5">
          <p className="label-eyebrow">Error 404</p>
          <h1 className="text-xl font-semibold tracking-tight">This page does not exist</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Continuum has no route registered for{" "}
            <code className="rounded bg-secondary/60 px-1 py-0.5 font-mono text-[11px]">
              {location.pathname}
            </code>
            . Check the link, or return to a page that does.
          </p>
        </div>
        <div className="flex items-center justify-center gap-2">
          <Button size="sm" asChild>
            <Link to="/dashboard">
              <LayoutDashboard className="h-4 w-4" />
              Go to dashboard
            </Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/">Back to landing</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
