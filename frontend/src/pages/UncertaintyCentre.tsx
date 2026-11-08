import { Link, useParams } from "react-router-dom";
import { Clock, HelpCircle, ShieldQuestion } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/common/States";
import { PageHeader, PanelSkeleton } from "@/components/common/PageHeader";
import { FreshnessBadge, SourceTypeBadge } from "@/components/common/StatusBadge";
import { ClaimCard } from "@/components/intelligence/ClaimCard";
import { useUncertainty } from "@/hooks/use-memory";
import { formatDateTime } from "@/lib/format";

export default function UncertaintyCentre() {
  const { projectId } = useParams<{ projectId: string }>();
  const uncertainty = useUncertainty(projectId);

  if (!projectId) return null;

  if (uncertainty.isLoading) return <PanelSkeleton rows={4} />;
  if (uncertainty.isError) {
    return (
      <ErrorState
        error={uncertainty.error}
        title="The uncertainty centre could not be loaded"
        onRetry={() => void uncertainty.refetch()}
      />
    );
  }

  const data = uncertainty.data;
  if (!data) return null;

  const empty =
    data.unsupported_claims.length === 0 &&
    data.open_questions.length === 0 &&
    data.stale_sources.length === 0;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Uncertainty Centre"
        title="What Continuum is unsure about"
        description="Unsupported claims, unanswered questions and sources flagged as potentially stale. Nothing here has been silently replaced or promoted."
      />

      {empty ? (
        <EmptyState
          icon={<ShieldQuestion className="h-4 w-4" />}
          title="Nothing is currently uncertain"
          description="Every extracted claim is supported by evidence, and no source has been flagged for freshness review."
        />
      ) : null}

      {data.unsupported_claims.length > 0 ? (
        <section className="space-y-3">
          <h2 className="label-eyebrow">
            Unsupported or conflicting claims · {data.unsupported_claims.length}
          </h2>
          <div className="space-y-3">
            {data.unsupported_claims.map((claim) => (
              <ClaimCard key={claim.id} projectId={projectId} claim={claim} />
            ))}
          </div>
        </section>
      ) : null}

      {data.open_questions.length > 0 ? (
        <section className="space-y-3">
          <h2 className="label-eyebrow">Open questions · {data.open_questions.length}</h2>
          <Card>
            <CardContent className="p-0">
              <ul className="divide-y divide-border/70">
                {data.open_questions.map((question) => (
                  <li key={question.id} className="flex items-start gap-3 p-4">
                    <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--status-warn))]" />
                    <div className="min-w-0">
                      <p className="text-sm leading-relaxed text-foreground">{question.question}</p>
                      {question.context ? (
                        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                          {question.context}
                        </p>
                      ) : null}
                      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                        {question.entity ? (
                          <span className="font-mono">{question.entity}</span>
                        ) : null}
                        <span>raised {formatDateTime(question.created_at)}</span>
                        <span className="uppercase tracking-wide">{question.status}</span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      ) : null}

      {data.stale_sources.length > 0 ? (
        <section className="space-y-3">
          <h2 className="label-eyebrow">Potentially stale sources · {data.stale_sources.length}</h2>
          <Card>
            <CardContent className="p-0">
              <ul className="divide-y divide-border/70">
                {data.stale_sources.map((source) => (
                  <li key={source.id} className="flex flex-wrap items-center gap-3 p-4">
                    <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <Link
                        to={`/sources/${source.id}`}
                        className="truncate text-sm text-foreground hover:underline"
                      >
                        {source.source_name}
                      </Link>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                        {source.author ? <span>Author · {source.author}</span> : null}
                        <span>Source date · {formatDateTime(source.created_at_source)}</span>
                        <span>Checked {formatDateTime(source.freshness_checked_at)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <SourceTypeBadge sourceType={source.source_type} />
                      <FreshnessBadge status={source.freshness} />
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            An older source is not automatically wrong. These are flagged for human review rather
            than replaced.
          </p>
        </section>
      ) : null}
    </div>
  );
}
