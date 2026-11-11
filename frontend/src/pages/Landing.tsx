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
import { useHealth } from "@/hooks/use-dashboard";
import { usePageTitle } from "@/hooks/use-page-title";

const WORKFLOW = [
  {
    label: "Connect",
    detail: "Authorise GitHub and bring in PDF, Markdown, text and ZIP documents.",
  },
  {
    label: "Reconstruct",
    detail: "Normalise commits, issues, pull requests and files into a single source record.",
  },
  {
    label: "Verify",
    detail: "Check claims against the evidence that produced them. Not active in this build.",
  },
  {
    label: "Review",
    detail: "A person approves what is true. Nothing is marked Verified without that step.",
  },
  {
    label: "Handover",
    detail: "A continuity brief the next owner can trust. Prepared, not generated yet.",
  },
];

const PROBLEMS = [
  {
    title: "Decisions live in threads",
    body: "The reason a service owns refunds is buried in a pull request, a commit message and a PDF nobody reopened.",
  },
  {
    title: "Ownership walks out",
    body: "When the person who held the context leaves, the next engineer inherits activity, not judgement.",
  },
  {
    title: "Handovers are reconstructed from memory",
    body: "Documents written at the last minute miss dependencies, open risks and the conflicts between sources.",
  },
];

const CAPABILITIES = [
  {
    Icon: GitBranch,
    title: "GitHub ingestion",
    body: "Server-side OAuth. Commits, issues, pull requests, README and permitted text files become sources. Tokens never touch the browser.",
  },
  {
    Icon: FileSearch,
    title: "Document intake",
    body: "PDF, Markdown, TXT and ZIP are processed with size limits, decompression limits and zip-slip protection.",
  },
  {
    Icon: ShieldCheck,
    title: "Secret scanning",
    body: "Keys, tokens and credential assignments are redacted before content is stored. Secrets are never kept.",
  },
  {
    Icon: ScrollText,
    title: "Evidence contracts",
    body: "Claim and verification types already exist so a later reviewer workflow plugs into a stable contract.",
  },
];

function HeroPreview() {
  return (
    <div className="panel overflow-hidden" aria-hidden="true">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Preview
          </p>
          <p className="mt-1 text-sm text-sand">Payments service</p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wider text-primary">Active</span>
      </div>
      <div className="grid sm:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="border-b border-border p-4 sm:border-b-0 sm:border-r">
          <p className="label-eyebrow">Activity</p>
          <ol className="mt-3 space-y-3">
            {[
              ["09:14", "Commit", "Retry refunds in the worker"],
              ["08:02", "Issue", "Checkout still owns the timeout"],
              ["Yesterday", "Pull request", "Move ownership to payments"],
            ].map(([time, kind, title]) => (
              <li key={title} className="grid grid-cols-[72px_1fr] gap-3 text-xs">
                <span className="font-mono text-[11px] text-muted-foreground">{time}</span>
                <span>
                  <span className="text-muted-foreground">{kind}</span>
                  <span className="mt-0.5 block text-foreground">{title}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
        <div className="space-y-4 p-4">
          <div>
            <p className="label-eyebrow">Sources</p>
            <p className="mt-2 text-sm">GitHub · 3 records</p>
            <p className="text-sm text-muted-foreground">architecture.pdf · parsed</p>
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-border pt-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                Claims
              </p>
              <p className="mt-1 text-sm text-status-ok">Verified 0</p>
            </div>
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                Conflicts
              </p>
              <p className="mt-1 text-sm text-status-warn">Open 0</p>
            </div>
          </div>
          <p className="border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
            Dependency · payments worker → checkout timeout. Illustration only.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  usePageTitle("Project Continuity");
  const health = useHealth();

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-[1180px] items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/" className="wordmark">
            Continuum
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden items-center gap-2 font-mono text-[11px] text-muted-foreground sm:flex">
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
              <Link to="/dashboard">Explore Demo</Link>
            </Button>
            <Button size="sm" asChild>
              <Link to="/dashboard">Get Started</Link>
            </Button>
          </div>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-[1180px] gap-12 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:items-center lg:px-8 lg:py-24">
          <div>
            <p className="label-eyebrow">Project continuity, reimagined.</p>
            <h1 className="mt-5 font-display text-5xl font-medium leading-[0.95] tracking-tight text-sand sm:text-6xl">
              People leave.
              <br />
              Knowledge stays.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-foreground/80">
              Continuum reconstructs the decisions, dependencies and unfinished work hidden across
              your project history, turning scattered activity into a handover your next team
              member can trust.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" asChild>
                <Link to="/dashboard">
                  Get Started
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button variant="outline" size="lg" asChild>
                <a href="#how-it-works">How It Works</a>
              </Button>
            </div>
            <p className="mt-5 font-mono text-[11px] text-muted-foreground">
              Team Cipher · No sign-in required · Public demo environment
            </p>
          </div>
          <HeroPreview />
        </section>

        <section className="border-t border-border">
          <div className="mx-auto max-w-[1180px] px-4 py-16 sm:px-6 lg:px-8">
            <p className="label-eyebrow">The problem</p>
            <h2 className="mt-3 max-w-xl font-display text-3xl font-medium tracking-tight text-sand">
              Project memory is scattered, then it leaves with the person who held it.
            </h2>
            <div className="mt-10 grid gap-px bg-border sm:grid-cols-3">
              {PROBLEMS.map((item) => (
                <article key={item.title} className="bg-background p-6">
                  <h3 className="font-display text-lg font-medium text-sand">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{item.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="border-t border-border">
          <div className="mx-auto max-w-[1180px] px-4 py-16 sm:px-6 lg:px-8">
            <p className="label-eyebrow">How Continuum works</p>
            <h2 className="mt-3 font-display text-3xl font-medium tracking-tight text-sand">
              Connect → Reconstruct → Verify → Review → Handover
            </h2>
            <ol className="mt-10 grid gap-4 md:grid-cols-5">
              {WORKFLOW.map((stage, index) => (
                <li key={stage.label} className="border-t border-border pt-4">
                  <span className="font-mono text-[11px] text-primary">0{index + 1}</span>
                  <h3 className="mt-3 font-display text-lg font-medium text-sand">{stage.label}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{stage.detail}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t border-border">
          <div className="mx-auto grid max-w-[1180px] gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:px-8">
            <div>
              <p className="label-eyebrow">Evidence</p>
              <h2 className="mt-3 font-display text-3xl font-medium tracking-tight text-sand">
                A claim is only as strong as the record behind it.
              </h2>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-muted-foreground">
                The inspection view keeps the extracted text, the author, the timestamp and the
                repository or document it came from. Later verification will cite those spans. It
                does not invent them today.
              </p>
              <div className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
                <BadgeCheck className="h-4 w-4 text-status-ok" />
                Only a human reviewer can mark a claim as Verified.
              </div>
            </div>
            <div className="panel p-5">
              <div className="flex items-center justify-between">
                <p className="text-sm">Refund ownership</p>
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Specimen
                </span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                “Retries belong to the payments worker.” Supported by commit message and issue
                #218. Conflict with an older README note is flagged, not resolved.
              </p>
              <div className="mt-4 flex flex-wrap gap-2 font-mono text-[11px] text-muted-foreground">
                <span className="rounded-md border border-border px-2 py-1">commit</span>
                <span className="rounded-md border border-border px-2 py-1">issue #218</span>
                <span className="rounded-md border border-border px-2 py-1 text-status-warn">
                  conflict
                </span>
              </div>
            </div>
          </div>
        </section>

        <section className="border-t border-border">
          <div className="mx-auto max-w-[1180px] px-4 py-16 sm:px-6 lg:px-8">
            <p className="label-eyebrow">Capabilities</p>
            <h2 className="mt-3 font-display text-3xl font-medium tracking-tight text-sand">
              What the platform does now
            </h2>
            <div className="mt-10 grid gap-4 sm:grid-cols-2">
              {CAPABILITIES.map(({ Icon, title, body }) => (
                <article key={title} className="panel p-5">
                  <Icon className="h-4 w-4 text-primary" />
                  <h3 className="mt-4 font-display text-lg font-medium text-sand">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-border">
          <div className="mx-auto grid max-w-[1180px] gap-8 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:px-8">
            <div>
              <p className="label-eyebrow">Security and privacy</p>
              <h2 className="mt-3 font-display text-3xl font-medium tracking-tight text-sand">
                Access stays where it was granted.
              </h2>
            </div>
            <ul className="space-y-4 text-sm leading-relaxed text-muted-foreground">
              <li className="flex gap-3">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                GitHub tokens are exchanged and stored on the server. The browser only starts the
                redirect.
              </li>
              <li className="flex gap-3">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                Every API request re-checks workspace membership. The interface does not decide who
                you are.
              </li>
              <li className="flex gap-3">
                <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                Uploaded archives are bounded. Path traversal is rejected before a file is stored.
              </li>
            </ul>
          </div>
        </section>

        <section className="border-t border-border">
          <div className="mx-auto flex max-w-[1180px] flex-col items-start justify-between gap-6 px-4 py-16 sm:px-6 lg:flex-row lg:items-end lg:px-8">
            <div>
              <h2 className="font-display text-4xl font-medium tracking-tight text-sand">
                Keep the knowledge.
              </h2>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
                Sign in, create a workspace, and connect a repository or upload the documents the
                project already has.
              </p>
            </div>
            <Button size="lg" asChild>
              <Link to="/dashboard">
                Get Started
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-3 px-4 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span className="wordmark text-[11px]">Continuum</span>
          <span>© {new Date().getFullYear()} Team Cipher · Agentic Project Continuity Platform</span>
          <span className="font-mono text-[11px]">Connect → Reconstruct → Verify → Review → Handover</span>
        </div>
      </footer>
    </div>
  );
}
