import { Link } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  FileSearch,
  GitBranch,
  Lock,
  ScrollText,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useHealth } from "@/hooks/use-dashboard";

const WORKFLOW = [
  { label: "Connect", detail: "Authorised GitHub and uploaded documents", shipped: true },
  { label: "Reconstruct", detail: "Normalised, hashed, de-duplicated sources", shipped: true },
  { label: "Verify", detail: "Evidence-backed claim checking", shipped: false },
  { label: "Review", detail: "Human reviewer approval", shipped: false },
  { label: "Handover", detail: "Generated continuity brief", shipped: false },
];

const CAPABILITIES = [
  {
    Icon: GitBranch,
    title: "GitHub ingestion",
    body: "Server-side OAuth. Commits, issues, pull requests, README and permitted text files are normalised into sources. Tokens never touch the browser.",
  },
  {
    Icon: FileSearch,
    title: "Document intake",
    body: "PDF, Markdown, TXT and ZIP processed with PyMuPDF and hardened archive handling — zip-slip protection, size and decompression limits.",
  },
  {
    Icon: ShieldCheck,
    title: "Secret scanning",
    body: "Every artefact is scanned for API keys, tokens and credential assignments before any content reaches a future AI workflow. Secrets are redacted, never stored.",
  },
  {
    Icon: ScrollText,
    title: "Evidence contracts",
    body: "Typed claim and verification schemas ship today so Phase 3 agents plug into a stable contract — with human-only approval enforced.",
  },
];

export default function Landing() {
  const health = useHealth();

  return (
    <div className="min-h-screen">
      <header className="border-b border-border/70">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md border border-primary/40 bg-primary/10">
              <Lock className="h-3.5 w-3.5 text-primary" />
            </span>
            <span className="text-sm font-semibold tracking-tight">Continuum</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-2 text-[11px] text-muted-foreground sm:flex">
              <span
                className={
                  health.isSuccess
                    ? "h-1.5 w-1.5 rounded-full bg-status-ok"
                    : health.isError
                      ? "h-1.5 w-1.5 rounded-full bg-status-danger"
                      : "h-1.5 w-1.5 rounded-full bg-status-warn"
                }
              />
              {health.isSuccess ? `API v${health.data?.version}` : "API status unknown"}
            </span>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/login">Sign in</Link>
            </Button>
            <Button size="sm" asChild>
              <Link to="/login">Get started</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8">
        <section className="grid gap-10 py-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:py-24">
          <div className="max-w-2xl">
            <Badge variant="outline" className="mb-5">
              CodeZen India 2026 · Team Cipher
            </Badge>
            <h1 className="text-3xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
              People may leave.
              <br />
              <span className="text-muted-foreground">The knowledge shouldn&apos;t have to.</span>
            </h1>
            <p className="mt-6 max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
              Continuum reconstructs project knowledge from authorised sources — repositories,
              commits, issues, pull requests and documents — so a departure no longer takes the
              project&apos;s memory with it.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" asChild>
                <Link to="/login">
                  Open the platform
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" size="lg" asChild>
                <Link to="/login">Connect a repository</Link>
              </Button>
            </div>
            <p className="mt-4 text-[11px] text-muted-foreground">
              Phase 1 foundation and Phase 2 ingestion are implemented. AI agents are Phase 3 and
              are not presented as complete.
            </p>
          </div>

          <div className="panel self-start p-5">
            <p className="label-eyebrow">Continuity pipeline</p>
            <ol className="mt-4 space-y-3">
              {WORKFLOW.map((stage, index) => (
                <li key={stage.label} className="flex items-start gap-3">
                  <span
                    className={
                      stage.shipped
                        ? "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary/50 text-[10px] font-medium text-primary"
                        : "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border text-[10px] font-medium text-muted-foreground"
                    }
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium">{stage.label}</p>
                      {stage.shipped ? (
                        <Badge variant="ok" className="px-1.5 py-0">
                          Shipped
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="px-1.5 py-0">
                          Phase 3
                        </Badge>
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">{stage.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-5 flex items-center gap-2 border-t border-border/70 pt-4 text-[11px] text-muted-foreground">
              <BadgeCheck className="h-3.5 w-3.5 text-status-ok" />
              Only a human reviewer can mark a claim as Verified.
            </div>
          </div>
        </section>

        <section className="border-t border-border/70 py-14">
          <p className="label-eyebrow">Implemented today</p>
          <h2 className="mt-2 text-xl font-semibold tracking-tight sm:text-2xl">
            Ingestion you can audit
          </h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {CAPABILITIES.map(({ Icon, title, body }) => (
              <div key={title} className="panel p-5">
                <Icon className="h-4 w-4 text-primary" />
                <h3 className="mt-3 text-sm font-medium">{title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="border-t border-border/70 py-14">
          <div className="panel flex flex-col items-start justify-between gap-5 p-6 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-base font-semibold tracking-tight">
                Reconstruct the project memory
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Sign in, create a workspace, and connect a repository or upload documents.
              </p>
            </div>
            <Button asChild>
              <Link to="/login">
                Continue
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/70">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-2 px-4 py-6 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>Continuum · Agentic Project Continuity Platform</span>
          <span>Connect → Reconstruct → Verify → Review → Handover</span>
        </div>
      </footer>
    </div>
  );
}
