import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  CircleDashed,
  FileDown,
  FileText,
  History,
  Loader2,
  Lock,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  ScrollText,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  TriangleAlert,
  Undo2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/common/PageHeader";
import { ProjectWorkspaceNav } from "@/components/common/ProjectWorkspaceNav";
import { EmptyState, ErrorState } from "@/components/common/States";
import { Tooltip } from "@/components/common/Tooltip";
import { useProject } from "@/hooks/use-projects";
import { usePageTitle } from "@/hooks/use-page-title";
import {
  useClaims,
  useGenerateHandover,
  useHandover,
  useHandoverLifecycle,
  useHandovers,
  useHandoverVersions,
  useUpdateHandover,
} from "@/hooks/use-memory";
import { HANDOVER_STATUS_META, STATEMENT_TYPE_META, claimTypeMeta } from "@/lib/intelligence-meta";
import { formatDateTime, pluralise } from "@/lib/format";
import { hasAtLeast } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { ApiClientError, toErrorMessage } from "@/services/api";
import { downloadHandover, type HandoverExportFormat } from "@/services/memory";
import { createSuccessorHandover, downloadSuccessorHandover, downloadSuccessorHandoverPdf, getSuccessorHandover, getSuccessorVerification, recordSuccessorVerification, transitionSuccessorHandover, type SavedSuccessorHandover } from "@/services/handover-intelligence";
import type {
  ClaimSummary,
  Handover,
  HandoverStatement,
  HandoverUpdateInput,
  HandoverVersion,
  StatementType,
} from "@/types";

// ---------------------------------------------------------------------------
// Read-only rendering
// ---------------------------------------------------------------------------
function ClaimRefChip({
  projectId,
  claimId,
  claim,
}: {
  projectId: string;
  claimId: string;
  claim: ClaimSummary | undefined;
}) {
  const meta = claim ? claimTypeMeta(claim.claim_type) : null;
  const Icon = meta?.Icon ?? BadgeCheck;
  return (
    <Link
      to={`/projects/${projectId}/memory/claims/${claimId}`}
      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border/70 bg-card/50 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
      title={claim ? claim.text : "Open the referenced claim"}
    >
      <Icon className="h-3 w-3 shrink-0" />
      <span className="truncate">{claim ? claim.text : `claim ${claimId.slice(0, 8)}`}</span>
    </Link>
  );
}

function StatementTypeBadge({ type }: { type: StatementType }) {
  const meta = STATEMENT_TYPE_META[type];
  return (
    <Tooltip label={meta.hint}>
      <Badge variant={meta.tone}>{meta.label}</Badge>
    </Tooltip>
  );
}

function StatementRow({
  projectId,
  statement,
  claimMap,
}: {
  projectId: string;
  statement: HandoverStatement;
  claimMap: Map<string, ClaimSummary>;
}) {
  return (
    <li className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatementTypeBadge type={statement.statement_type} />
        {statement.reviewer_edited ? <Badge variant="info">Reviewer edited</Badge> : null}
        {statement.unsupported ? (
          <Tooltip label="This statement is not backed by an approved claim and cannot enter an approved handover.">
            <Badge variant="danger" className="gap-1">
              <TriangleAlert className="h-3 w-3" />
              Not evidence-backed
            </Badge>
          </Tooltip>
        ) : null}
      </div>
      <p className="text-sm leading-relaxed text-foreground">{statement.text}</p>
      {statement.original_text && statement.original_text !== statement.text ? (
        <p className="text-[11px] italic leading-relaxed text-muted-foreground">
          Original: {statement.original_text}
        </p>
      ) : null}
      {statement.claim_ids.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {statement.claim_ids.map((claimId) => (
            <ClaimRefChip
              key={claimId}
              projectId={projectId}
              claimId={claimId}
              claim={claimMap.get(claimId)}
            />
          ))}
        </div>
      ) : null}
    </li>
  );
}

function ValidationPanel({ version }: { version: HandoverVersion }) {
  if (version.validation_errors.length === 0) return null;
  return (
    <Card className="border-dashed border-status-danger/40">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <TriangleAlert className="h-3.5 w-3.5 text-status-danger" />
          Output validator — rejected or unresolved statements
        </CardTitle>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {version.validation_errors.length}
        </span>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          The Handover Writer never invents references. Statements it could not tie to an approved
          claim were removed and recorded here. This version cannot be approved until every factual
          statement is backed by an approved claim.
        </p>
        {version.validation_errors.map((error, index) => (
          <div
            key={index}
            className="rounded-md border border-border/70 bg-card/40 p-2.5 text-[11px] leading-relaxed text-muted-foreground"
          >
            <span className="font-mono uppercase tracking-wider">
              {String(error.code ?? "issue")}
            </span>
            {error.section ? <span> · {String(error.section)}</span> : null}
            {error.message ? <p className="mt-1 text-foreground/90">{String(error.message)}</p> : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function VersionDocument({
  projectId,
  version,
  claimMap,
}: {
  projectId: string;
  version: HandoverVersion;
  claimMap: Map<string, ClaimSummary>;
}) {
  return (
    <div className="space-y-4">
      <div className="panel flex flex-col gap-2 border border-border p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5" />
          Written from {pluralise(version.included_claim_ids.length, "approved claim")} only.
          Unlinked sentences are deleted by the output validator.
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
          <span>v{version.version_number}</span>
          <span>Generated {formatDateTime(version.created_at)}</span>
          {version.model_name ? (
            <span className="font-mono">model {version.model_name}</span>
          ) : null}
        </div>
      </div>

      {version.included_claim_ids.length === 0 ? (
        <div className="panel border border-border p-4">
          <p className="text-xs leading-relaxed text-muted-foreground">
            No claims have been approved for this project yet, so the handover contains no
            statements. A claim is only included here after a human reviewer marks it{" "}
            <span className="text-foreground">Verified</span>.
          </p>
        </div>
      ) : null}

      {version.summary ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-foreground">{version.summary}</p>
          </CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {version.sections
          .filter((section) => !section.removed)
          .map((section) => (
            <Card key={section.key}>
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  {section.title}
                </CardTitle>
                {section.not_established ? (
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                    Not established
                  </span>
                ) : null}
              </CardHeader>
              <CardContent>
                {section.statements.length > 0 ? (
                  <ul className="space-y-3">
                    {section.statements.map((statement) => (
                      <StatementRow
                        key={statement.statement_id}
                        projectId={projectId}
                        statement={statement}
                        claimMap={claimMap}
                      />
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {section.placeholder ??
                      "No approved claim covers this section, so nothing was written for it."}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
      </div>

      {version.reviewer_notes.length > 0 ? (
        <Card className="border-dashed">
          <CardHeader>
            <CardTitle className="text-xs font-medium text-muted-foreground">Reviewer notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {version.reviewer_notes.map((note) => (
              <div
                key={note.id}
                className="rounded-md border border-border/70 bg-card/40 p-2.5 text-xs leading-relaxed text-foreground"
              >
                {note.text}
                <span className="ml-2 text-[11px] text-muted-foreground">
                  {formatDateTime(note.created_at)}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <ValidationPanel version={version} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------
interface DraftStatement {
  statement_id: string | null;
  text: string;
  /** The text as loaded, so an unchanged statement is never flagged as edited. */
  baseline: string;
  original_text: string | null;
  claim_ids: string[];
  statement_type: StatementType;
  unsupported: boolean;
  removed: boolean;
}

interface DraftSection {
  key: string;
  title: string;
  statements: DraftStatement[];
  removed: boolean;
}

interface Draft {
  title: string;
  summary: string;
  sections: DraftSection[];
  notes: string[];
  note: string;
}

function buildDraft(version: HandoverVersion, title: string): Draft {
  return {
    title,
    summary: version.summary ?? "",
    sections: version.sections.map((section) => ({
      key: section.key,
      title: section.title,
      removed: section.removed,
      statements: section.statements.map((statement) => ({
        statement_id: statement.statement_id,
        text: statement.text,
        baseline: statement.text,
        original_text: statement.original_text,
        claim_ids: statement.claim_ids,
        statement_type: statement.statement_type,
        unsupported: statement.unsupported,
        removed: false,
      })),
    })),
    notes: [],
    note: "",
  };
}

function SectionEditor({
  section,
  onChange,
}: {
  section: DraftSection;
  onChange: (next: DraftSection) => void;
}) {
  const updateStatement = (index: number, next: DraftStatement) => {
    const statements = section.statements.map((item, position) =>
      position === index ? next : item,
    );
    onChange({ ...section, statements });
  };

  const setText = (index: number, text: string) => {
    const current = section.statements[index];
    // Record the original the first time the reviewer rewrites generated text.
    const original_text =
      text === current.baseline
        ? current.original_text
        : (current.original_text ?? current.baseline);
    updateStatement(index, { ...current, text, original_text });
  };

  return (
    <Card className={cn(section.removed && "opacity-60")}>
      <CardHeader className="space-y-2">
        <div className="flex items-center gap-2">
          <Input
            value={section.title}
            onChange={(event) => onChange({ ...section, title: event.target.value })}
            aria-label="Section title"
            className="h-8 max-w-md text-sm"
          />
          <Button
            type="button"
            size="sm"
            variant={section.removed ? "default" : "ghost"}
            className="ml-auto"
            onClick={() => onChange({ ...section, removed: !section.removed })}
          >
            {section.removed ? <Undo2 className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
            {section.removed ? "Keep section" : "Remove section"}
          </Button>
        </div>
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          {section.key}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {section.statements.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">
            No approved claim covers this section. A section with no content is exported as a
            “not established” placeholder rather than invented prose.
          </p>
        ) : null}
        {section.statements.map((statement, index) => (
          <div
            key={statement.statement_id ?? index}
            className={cn(
              "space-y-2 rounded-md border border-border/70 bg-card/40 p-3",
              statement.removed && "opacity-50",
            )}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <StatementTypeBadge type={statement.statement_type} />
              {statement.claim_ids.length > 0 ? (
                <Badge variant="secondary">
                  {pluralise(statement.claim_ids.length, "claim")}
                </Badge>
              ) : (
                <Badge variant="warn">No claim reference</Badge>
              )}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="ml-auto h-7"
                onClick={() => updateStatement(index, { ...statement, removed: !statement.removed })}
              >
                {statement.removed ? (
                  <Undo2 className="h-3.5 w-3.5" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                {statement.removed ? "Restore" : "Remove"}
              </Button>
            </div>
            <Textarea
              value={statement.text}
              onChange={(event) => setText(index, event.target.value)}
              rows={2}
              disabled={statement.removed}
              aria-label="Statement text"
            />
            <p className="text-[10px] leading-relaxed text-muted-foreground">
              Claim references are re-resolved by the server against the approved set — the browser
              can never widen what counts as evidence.
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function HandoverEditor({
  version,
  title,
  projectId,
  onSave,
  onCancel,
  saving,
}: {
  version: HandoverVersion;
  title: string;
  projectId: string;
  onSave: (input: HandoverUpdateInput) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<Draft>(() => buildDraft(version, title));
  const [noteText, setNoteText] = useState("");

  // Reset when a different version is loaded.
  useEffect(() => {
    setDraft(buildDraft(version, title));
    setNoteText("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version.id]);

  const updateSection = (index: number, next: DraftSection) => {
    setDraft((current) => ({
      ...current,
      sections: current.sections.map((section, position) => (position === index ? next : section)),
    }));
  };

  const addNote = () => {
    const text = noteText.trim();
    if (text.length < 2) return;
    setDraft((current) => ({ ...current, notes: [...current.notes, text] }));
    setNoteText("");
  };

  const handleSave = () => {
    const sections = draft.sections.map((section) => ({
      key: section.key,
      title: section.title.trim() || null,
      removed: section.removed,
      statements: section.statements
        .filter((statement) => !statement.removed && statement.text.trim())
        .map((statement) => ({
          statement_id: statement.statement_id,
          text: statement.text.trim(),
          claim_ids: statement.claim_ids,
          original_text: statement.original_text,
        })),
    }));
    onSave({
      title: draft.title.trim() || null,
      summary: draft.summary.trim() || null,
      sections,
      reviewer_notes: draft.notes,
      note: draft.note.trim() || null,
    });
  };

  return (
    <div className="space-y-4">
      <div className="panel flex flex-col gap-3 border border-primary/30 bg-primary/[0.04] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
          <Pencil className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          Saving writes a new immutable version. The current version is never overwritten, and a
          published version is never replaced.
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save as new version
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="handover-title">Document title</Label>
          <Input
            id="handover-title"
            value={draft.title}
            onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="handover-note">Why are you editing? (recorded in the audit trail)</Label>
          <Input
            id="handover-note"
            value={draft.note}
            placeholder="e.g. clarified the deployment owner"
            onChange={(event) => setDraft((current) => ({ ...current, note: event.target.value }))}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="handover-summary">Summary</Label>
        <Textarea
          id="handover-summary"
          value={draft.summary}
          rows={3}
          placeholder="A summary is only kept when it can be traced to an approved claim."
          onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))}
        />
      </div>

      <div className="space-y-3">
        {draft.sections.map((section, index) => (
          <SectionEditor
            key={section.key}
            section={section}
            onChange={(next) => updateSection(index, next)}
          />
        ))}
      </div>

      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Reviewer notes — appended to this version
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            A reviewer note is authored by you and is never presented as an established project
            fact.
          </p>
          {draft.notes.length > 0 ? (
            <ul className="space-y-1.5">
              {draft.notes.map((text, index) => (
                <li
                  key={index}
                  className="rounded-md border border-border/70 bg-card/40 p-2.5 text-xs text-foreground"
                >
                  {text}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="flex items-center gap-2">
            <Input
              value={noteText}
              onChange={(event) => setNoteText(event.target.value)}
              placeholder="Add a reviewer note"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addNote();
                }
              }}
            />
            <Button type="button" size="sm" variant="outline" onClick={addNote}>
              <Plus className="h-3.5 w-3.5" />
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      <p className="text-[11px] text-muted-foreground">
        Project {projectId.slice(0, 8)} · editing version {version.version_number}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Version history
// ---------------------------------------------------------------------------
function VersionHistory({
  projectId,
  handover,
  versions,
  claimMap,
}: {
  projectId: string;
  handover: Handover;
  versions: HandoverVersion[];
  claimMap: Map<string, ClaimSummary>;
}) {
  const { toast } = useToast();
  const [openId, setOpenId] = useState<string | null>(null);

  const doExport = async (version: HandoverVersion, format: HandoverExportFormat) => {
    try {
      await downloadHandover(
        projectId,
        handover.id,
        format,
        `handover-v${version.version_number}.${format}`,
        version.version_number,
      );
      toast({
        title: "Export started",
        description: `v${version.version_number} is downloading as .${format}. Every download is audited.`,
        variant: "success",
      });
    } catch (caught) {
      toast({
        title: "Could not export the handover",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  if (versions.length === 0) {
    return (
      <EmptyState
        icon={<History className="h-4 w-4" />}
        title="No versions yet"
        description="Generating the handover creates its first version."
      />
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Every version is immutable. Editing a handover appends a new version rather than changing an
        existing one; a published version is never overwritten.
      </p>
      {versions.map((version) => {
        const meta = HANDOVER_STATUS_META[version.status];
        const open = openId === version.id;
        return (
          <Card key={version.id}>
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2 space-y-0">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono">
                  v{version.version_number}
                </Badge>
                <Badge variant={meta.tone}>{meta.label}</Badge>
                {version.version_number === handover.current_version ? (
                  <Badge variant="secondary">Current</Badge>
                ) : null}
                <span className="text-[11px] text-muted-foreground">
                  {formatDateTime(version.created_at)}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {pluralise(version.included_claim_ids.length, "claim")}
                </span>
                {version.validation_errors.length > 0 ? (
                  <Badge variant="danger" className="gap-1">
                    <TriangleAlert className="h-3 w-3" />
                    {version.validation_errors.length} issue
                    {version.validation_errors.length === 1 ? "" : "s"}
                  </Badge>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setOpenId(open ? null : version.id)}
                >
                  {open ? "Hide" : "Preview"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => void doExport(version, "md")}>
                  <FileText className="h-3.5 w-3.5" />
                  MD
                </Button>
                <Button size="sm" variant="outline" onClick={() => void doExport(version, "pdf")}>
                  <FileDown className="h-3.5 w-3.5" />
                  PDF
                </Button>
              </div>
            </CardHeader>
            {open ? (
              <CardContent>
                <VersionDocument projectId={projectId} version={version} claimMap={claimMap} />
              </CardContent>
            ) : null}
          </Card>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function HandoverPreview() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useProject(projectId);
  usePageTitle(project.data ? `Handover — ${project.data.name}` : "Handover");
  const handovers = useHandovers(projectId);
  const { toast } = useToast();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [successorRole, setSuccessorRole] = useState("project_maintainer");
  const [customSuccessorRole, setCustomSuccessorRole] = useState("");
  const [savedSuccessorPackage, setSavedSuccessorPackage] = useState<SavedSuccessorHandover | null>(null);
  const resolvedSuccessorRole = successorRole === "__custom__" ? (customSuccessorRole.trim() || "custom") : successorRole;
  const successor = useQuery({
    queryKey: ["successor-handover", projectId, resolvedSuccessorRole],
    queryFn: () => getSuccessorHandover(projectId as string, resolvedSuccessorRole),
    enabled: Boolean(projectId) && (successorRole !== "__custom__" || customSuccessorRole.trim().length > 0),
  });
  const verification = useQuery({
    queryKey: ["successor-verification", projectId, savedSuccessorPackage?.id],
    queryFn: () => getSuccessorVerification(projectId as string, savedSuccessorPackage?.id as string),
    enabled: Boolean(projectId && savedSuccessorPackage?.id),
  });
  const saveSuccessorDraft = async () => {
    if (!projectId) return;
    try {
      setSavedSuccessorPackage(await createSuccessorHandover(projectId, resolvedSuccessorRole));
      toast({ title: "Successor handover saved", description: "A snapshot-bound draft revision was preserved." , variant: "success" });
    } catch (error) {
      toast({ title: "Could not save successor handover", description: toErrorMessage(error), variant: "error" });
    }
  };
  const transitionSavedPackage = async (action: "submit" | "approve") => {
    if (!projectId || !savedSuccessorPackage) return;
    try {
      setSavedSuccessorPackage(await transitionSuccessorHandover(projectId, savedSuccessorPackage.id, action));
      toast({ title: action === "submit" ? "Submitted for review" : "Successor handover approved", description: "The package status was recorded." , variant: "success" });
    } catch (error) {
      toast({ title: "Could not update handover status", description: toErrorMessage(error), variant: "error" });
    }
  };
  const verifyOnboardingStep = async (step: { title: string; phase: string }) => {
    if (!projectId || !savedSuccessorPackage) return;
    const activity = step.phase === "orientation" || step.phase === "codebase" ? "architecture_understanding" : step.phase === "environment" ? "environment_setup" : step.phase === "history" ? "historical_context" : step.phase === "work" || step.phase === "contribution" ? "independent_task" : "dependency_understanding";
    try {
      await recordSuccessorVerification(projectId, savedSuccessorPackage.id, activity, `Successor confirmed completion of: ${step.title}`);
      await verification.refetch();
      toast({ title: "Verification recorded", description: "This is a user-confirmed activity, not an inferred completion.", variant: "success" });
    } catch (error) {
      toast({ title: "Could not record verification", description: toErrorMessage(error), variant: "error" });
    }
  };

  // Default to the most recent handover once the list loads.
  useEffect(() => {
    if (selectedId || !handovers.data) return;
    const first = handovers.data.items[0];
    if (first) setSelectedId(first.id);
  }, [handovers.data, selectedId]);

  const handover = useHandover(projectId, selectedId ?? undefined);
  const versions = useHandoverVersions(projectId, selectedId ?? undefined);

  const approvedClaims = useClaims(projectId, { status: "Verified", page_size: 100 });
  const claimMap = useMemo(
    () => new Map<string, ClaimSummary>((approvedClaims.data?.items ?? []).map((c) => [c.id, c])),
    [approvedClaims.data],
  );

  const generate = useGenerateHandover(projectId ?? "");
  const update = useUpdateHandover(projectId ?? "", selectedId ?? "");
  const lifecycle = useHandoverLifecycle(projectId ?? "", selectedId ?? "");

  if (!projectId) return null;

  const role = project.data?.workspace?.role ?? null;
  const canGenerate = hasAtLeast(role, "member");
  const canReview = hasAtLeast(role, "admin");

  const document = handover.data;
  const current = document?.current ?? null;
  const currentStatus = current?.status ?? document?.status ?? "Draft";
  const publishedVersion = versions.data?.find((version) => version.status === "Published") ?? null;

  const handleGenerate = async () => {
    try {
      const created = await generate.mutateAsync();
      setSelectedId(created.id);
      toast({
        title: "Handover generated",
        description: `${pluralise(created.current?.included_claim_ids.length ?? 0, "approved claim")} referenced.`,
        variant: "success",
      });
    } catch (caught) {
      const notConfigured = caught instanceof ApiClientError && caught.code === "ai_not_configured";
      toast({
        title: notConfigured ? "Intelligence layer not configured" : "Could not generate handover",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  const runLifecycle = async (
    label: string,
    fn: () => Promise<unknown>,
    success: string,
  ) => {
    try {
      await fn();
      toast({ title: label, description: success, variant: "success" });
    } catch (caught) {
      toast({ title: label, description: toErrorMessage(caught), variant: "error" });
    }
  };

  const handleSave = async (input: HandoverUpdateInput) => {
    try {
      await update.mutateAsync(input);
      setEditing(false);
      toast({
        title: "New version saved",
        description: "Your edit was stored as a new draft version for review.",
        variant: "success",
      });
    } catch (caught) {
      toast({
        title: "Could not save the edit",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  const doExportCurrent = async (format: HandoverExportFormat) => {
    if (!document || !current) return;
    try {
      await downloadHandover(
        projectId,
        document.id,
        format,
        `handover-v${current.version_number}.${format}`,
        current.version_number,
      );
      toast({
        title: "Export started",
        description: `v${current.version_number} is downloading as .${format}.`,
        variant: "success",
      });
    } catch (caught) {
      toast({
        title: "Could not export the handover",
        description: toErrorMessage(caught),
        variant: "error",
      });
    }
  };

  const isLoading = handovers.isLoading || (selectedId && handover.isLoading);
  const hasNone = !handovers.isLoading && (handovers.data?.items.length ?? 0) === 0;

  const generateButton = (
    <Button size="sm" onClick={() => void handleGenerate()} disabled={!canGenerate || generate.isPending}>
      {generate.isPending ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : document ? (
        <RefreshCw className="h-4 w-4" />
      ) : (
        <Sparkles className="h-4 w-4" />
      )}
      {document ? "Regenerate" : "Generate handover"}
    </Button>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Handover"
        title={document?.title ?? project.data?.name ?? "Handover"}
        description="A versioned handover assembled from approved claims only. Every statement links back to the claim it came from, and only a human reviewer can approve it."
        actions={
          <>
            <Button variant="ghost" size="sm" asChild>
              <Link to={`/projects/${projectId}`}>
                <ArrowLeft className="h-4 w-4" />
                Project
              </Link>
            </Button>
            {generateButton}
          </>
        }
      />

      <ProjectWorkspaceNav projectId={projectId} />

      {!canGenerate ? (
        <p className="text-[11px] text-muted-foreground">
          The member role is required to generate a handover; the admin role is required to edit,
          approve or publish one.
        </p>
      ) : null}

      {handovers.isError ? (
        <ErrorState
          error={handovers.error}
          title="The handovers could not be loaded"
          onRetry={() => void handovers.refetch()}
        />
      ) : isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-full rounded-lg" />
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-32 w-full rounded-lg" />
          ))}
        </div>
      ) : hasNone ? (
        <div className="space-y-4">
          <EmptyState
            icon={<ScrollText className="h-4 w-4" />}
            title="No claim-based handover generated yet"
            description="The successor plan below is assembled from repository snapshots and Stage 3–5 analysis. The claim-based document workflow remains available after reviewers approve project claims."
            action={<div className="flex items-center gap-2"><Button size="sm" variant="outline" asChild><Link to={`/projects/${projectId}/memory/claims?status=Verified`}><FileText className="h-4 w-4" />Review approved claims</Link></Button>{canGenerate ? generateButton : null}</div>}
          />
          <Card>
            <CardHeader><CardTitle className="text-sm">Snapshot successor plan</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Select value={successorRole} onValueChange={setSuccessorRole}><SelectTrigger className="h-9 w-64 text-xs"><SelectValue /></SelectTrigger><SelectContent>{[["project_maintainer", "Project maintainer"], ["backend_developer", "Backend developer"], ["frontend_developer", "Frontend developer"], ["full_stack_developer", "Full-stack developer"], ["ml_ai_engineer", "ML / AI engineer"], ["devops_infrastructure_engineer", "DevOps / infrastructure"], ["__custom__", "Custom role…"]].map(([value, label]) => <SelectItem key={value} value={value} className="text-xs">{label}</SelectItem>)}</SelectContent></Select>
                {successorRole === "__custom__" ? <Input className="h-9 w-56 text-xs" maxLength={40} placeholder="e.g. Security engineer" value={customSuccessorRole} onChange={(event) => setCustomSuccessorRole(event.target.value)} /> : null}
                <Button size="sm" onClick={() => void saveSuccessorDraft()} disabled={!canGenerate || successor.isLoading}>Save generated draft</Button>
                {savedSuccessorPackage ? <Badge variant={savedSuccessorPackage.status === "approved" ? "ok" : "secondary"}>v{savedSuccessorPackage.version} · {savedSuccessorPackage.status}</Badge> : null}
                {savedSuccessorPackage?.status === "draft" && canReview ? <Button size="sm" variant="outline" onClick={() => void transitionSavedPackage("submit")}>Submit for review</Button> : null}
                {savedSuccessorPackage?.status === "in_review" && canReview ? <Button size="sm" onClick={() => void transitionSavedPackage("approve")}>Approve</Button> : null}
                {successor.data ? <Button size="sm" variant="outline" onClick={() => void downloadSuccessorHandover(projectId, resolvedSuccessorRole)}>Download Markdown</Button> : null}
              </div>
              {successor.isLoading ? <Skeleton className="h-20 w-full rounded-lg" /> : successor.isError ? <p className="text-xs text-muted-foreground">{toErrorMessage(successor.error)} Connect a repository and run its analysis first.</p> : successor.data ? <><p className="text-xs text-muted-foreground">{successor.data.readiness.status.replace(/_/g, " ")} · snapshot {successor.data.snapshot_commit?.slice(0, 12) ?? successor.data.snapshot_branch} · {successor.data.tasks.length} suggested tasks</p><div className="grid gap-2 md:grid-cols-2">{successor.data.sections.map((section) => <div className="rounded-md border border-border p-3" key={section.key}><p className="text-xs font-medium">{section.title}</p><p className="mt-1 text-xs text-muted-foreground">{section.items.length ? `${section.items.length} evidence-linked item(s)` : "Not established in available evidence"}</p></div>)}</div></> : null}
            </CardContent>
          </Card>
        </div>
      ) : handover.isError ? (
        <ErrorState
          error={handover.error}
          title="The handover could not be loaded"
          onRetry={() => void handover.refetch()}
        />
      ) : document && current ? (
        <div className="space-y-5">
          {handovers.data && handovers.data.items.length > 1 ? (
            <div className="flex items-center gap-2">
              <Label htmlFor="handover-select" className="text-[11px]">
                Handover
              </Label>
              <Select
                value={selectedId ?? ""}
                onValueChange={(value) => {
                  setSelectedId(value);
                  setEditing(false);
                }}
              >
                <SelectTrigger id="handover-select" className="h-8 w-72 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {handovers.data.items.map((item) => (
                    <SelectItem key={item.id} value={item.id} className="text-xs">
                      {item.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {/* Status / lifecycle bar */}
          <div className="panel flex flex-wrap items-center gap-x-4 gap-y-2 border border-border p-4">
            <Badge variant={HANDOVER_STATUS_META[currentStatus].tone}>
              {HANDOVER_STATUS_META[currentStatus].label}
            </Badge>
            <span className="text-[11px] text-muted-foreground">
              current version <span className="font-mono">v{document.current_version}</span>
            </span>
            {current.approved_at ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <CheckCircle2 className="h-3 w-3 text-status-ok" />
                Approved {formatDateTime(current.approved_at)}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <CircleDashed className="h-3 w-3" />
                Not yet approved by a reviewer
              </span>
            )}

            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => void doExportCurrent("md")}>
                <FileText className="h-3.5 w-3.5" />
                Export MD
              </Button>
              <Button size="sm" variant="outline" onClick={() => void doExportCurrent("pdf")}>
                <FileDown className="h-3.5 w-3.5" />
                Export PDF
              </Button>

              {canReview && currentStatus !== "Archived" ? (
                editing ? null : (
                  <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                    <Pencil className="h-3.5 w-3.5" />
                    Edit
                  </Button>
                )
              ) : null}

              {canReview && currentStatus === "Draft" ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={lifecycle.submit.isPending}
                  onClick={() =>
                    void runLifecycle(
                      "Submitted for review",
                      () => lifecycle.submit.mutateAsync(),
                      "The draft is now awaiting approval.",
                    )
                  }
                >
                  {lifecycle.submit.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Send className="h-3.5 w-3.5" />
                  )}
                  Submit
                </Button>
              ) : null}

              {canReview && (currentStatus === "Draft" || currentStatus === "In Review") ? (
                <Button
                  size="sm"
                  disabled={lifecycle.approve.isPending}
                  onClick={() =>
                    void runLifecycle(
                      "Handover approved",
                      () => lifecycle.approve.mutateAsync(),
                      "Approved by a human reviewer. It can now be published.",
                    )
                  }
                >
                  {lifecycle.approve.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ShieldCheck className="h-3.5 w-3.5" />
                  )}
                  Approve
                </Button>
              ) : null}

              {canReview && currentStatus === "Approved" ? (
                <Button
                  size="sm"
                  disabled={lifecycle.publish.isPending}
                  onClick={() =>
                    void runLifecycle(
                      "Handover published",
                      () => lifecycle.publish.mutateAsync(),
                      "Published versions are immutable and available to the successor.",
                    )
                  }
                >
                  {lifecycle.publish.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  )}
                  Publish
                </Button>
              ) : null}

              {canReview && currentStatus !== "Archived" ? (
                <Tooltip label="Archiving keeps every version and its history.">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={lifecycle.archive.isPending}
                    onClick={() =>
                      void runLifecycle(
                        "Handover archived",
                        () => lifecycle.archive.mutateAsync(),
                        "The handover is archived; its versions are preserved.",
                      )
                    }
                  >
                    {lifecycle.archive.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Archive className="h-3.5 w-3.5" />
                    )}
                    Archive
                  </Button>
                </Tooltip>
              ) : null}
            </div>
          </div>

          {currentStatus === "Archived" ? (
            <div className="panel border border-border p-4 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-2">
                <Lock className="h-3.5 w-3.5" />
                This handover is archived. Its published versions remain readable and exportable.
              </span>
            </div>
          ) : null}

          {!canReview ? (
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              You have read-only access. Editing, approval and publishing are restricted to a
              workspace owner or admin, and are verified again on the server.
            </p>
          ) : null}

          <Tabs defaultValue="document">
            <TabsList>
              <TabsTrigger value="document">Document</TabsTrigger>
              <TabsTrigger value="successor-plan">Successor plan</TabsTrigger>
              <TabsTrigger value="versions">
                Versions
                {versions.data ? ` (${versions.data.length})` : ""}
              </TabsTrigger>
              {publishedVersion ? (
                <TabsTrigger value="successor">Successor view</TabsTrigger>
              ) : null}
            </TabsList>

            <TabsContent value="document">
              {editing && canReview ? (
                <HandoverEditor
                  version={current}
                  title={document.title}
                  projectId={projectId}
                  onSave={(input) => void handleSave(input)}
                  onCancel={() => setEditing(false)}
                  saving={update.isPending}
                />
              ) : (
                <VersionDocument projectId={projectId} version={current} claimMap={claimMap} />
              )}
            </TabsContent>

            <TabsContent value="successor-plan">
              <div className="space-y-4">
                <div className="panel flex flex-wrap items-center justify-between gap-3 border border-border p-4">
                  <div>
                    <p className="label-eyebrow">Snapshot-bound successor plan</p>
                    <p className="mt-1 text-xs text-muted-foreground">Built from persisted code, history, and knowledge analysis. This is a generated preview; it does not mark a handover approved.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                  <Select value={successorRole} onValueChange={setSuccessorRole}>
                    <SelectTrigger className="h-9 w-64 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[["project_maintainer", "Project maintainer"], ["backend_developer", "Backend developer"], ["frontend_developer", "Frontend developer"], ["full_stack_developer", "Full-stack developer"], ["ml_ai_engineer", "ML / AI engineer"], ["devops_infrastructure_engineer", "DevOps / infrastructure"], ["__custom__", "Custom role…"]].map(([value, label]) => <SelectItem key={value} value={value} className="text-xs">{label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {successorRole === "__custom__" ? <Input className="h-9 w-56 text-xs" maxLength={40} placeholder="e.g. Security engineer" value={customSuccessorRole} onChange={(event) => setCustomSuccessorRole(event.target.value)} /> : null}
                  </div>
                </div>
                {successor.isLoading ? <Skeleton className="h-32 w-full rounded-lg" /> : successor.isError ? <div className="panel border border-border p-4 text-xs text-muted-foreground">{toErrorMessage(successor.error)} Ensure repository ingestion and Stage 3–5 analyses have run.</div> : successor.data ? <>
                  <div className="panel flex flex-wrap items-center gap-4 border border-border p-4 text-xs">
                  <Badge variant={successor.data.readiness.status === "ready" ? "ok" : "warn"}>{successor.data.readiness.status.replace(/_/g, " ")}</Badge>
                    <span>Snapshot <span className="font-mono">{successor.data.snapshot_commit?.slice(0, 12) ?? successor.data.snapshot_branch}</span></span>
                    <span>{successor.data.source_coverage.files_processed}/{successor.data.source_coverage.files_discovered} files processed</span>
                    <span>{successor.data.source_coverage.knowledge_unit_count} knowledge records</span>
                    <Button size="sm" variant="outline" className="ml-auto" onClick={() => void downloadSuccessorHandover(projectId, resolvedSuccessorRole).catch((error) => toast({ title: "Could not export successor handover", description: toErrorMessage(error), variant: "error" }))}><FileText className="h-3.5 w-3.5" />Markdown</Button>
                    {savedSuccessorPackage ? <Button size="sm" variant="outline" onClick={() => void downloadSuccessorHandoverPdf(projectId, savedSuccessorPackage.id).catch((error) => toast({ title: "Could not export successor handover", description: toErrorMessage(error), variant: "error" }))}><FileDown className="h-3.5 w-3.5" />PDF</Button> : null}
                    <Button size="sm" variant="outline" onClick={() => void saveSuccessorDraft()}>{savedSuccessorPackage ? `Saved v${savedSuccessorPackage.version}` : "Save draft"}</Button>
                    {savedSuccessorPackage?.status === "draft" && canReview ? <Button size="sm" variant="outline" onClick={() => void transitionSavedPackage("submit")}>Submit for review</Button> : null}
                    {savedSuccessorPackage?.status === "in_review" && canReview ? <Button size="sm" onClick={() => void transitionSavedPackage("approve")}>Approve</Button> : null}
                    {savedSuccessorPackage?.status === "approved" ? <Badge variant="ok">Approved v{savedSuccessorPackage.version}</Badge> : null}
                  </div>
                  {successor.data.readiness.blockers.length ? <Card><CardHeader><CardTitle className="text-sm">Readiness blockers</CardTitle></CardHeader><CardContent className="space-y-2">{successor.data.readiness.blockers.map((item, index) => <div key={index} className="rounded-md border border-border p-3"><p className="text-xs font-medium">{item.title}</p><p className="mt-1 text-xs text-muted-foreground">{item.description}</p></div>)}</CardContent></Card> : null}
                  <div className="grid gap-4 lg:grid-cols-2">{successor.data.sections.map((section) => <Card key={section.key}><CardHeader><CardTitle className="text-sm">{section.title}</CardTitle></CardHeader><CardContent className="space-y-2">{section.items.length ? section.items.slice(0, 12).map((item, index) => <div key={index} className="border-l-2 border-primary/40 pl-3 text-xs"><p>{item.text ?? item.content ?? item.title}</p><div className="mt-1 flex flex-wrap gap-2 text-[10px] text-muted-foreground">{item.evidence_level ? <span>{item.evidence_level}</span> : null}{item.evidence?.map((ev, evIndex) => ev.url ? <a key={evIndex} className="text-primary underline" href={ev.url} target="_blank" rel="noreferrer">{ev.label ?? ev.file_path ?? "source"}</a> : <span key={evIndex}>{ev.file_path ?? ev.label}</span>)}</div></div>) : <p className="text-xs text-muted-foreground">Not established in available snapshot evidence.</p>}</CardContent></Card>)}</div>
                  <div className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle className="text-sm">Suggested tasks ({successor.data.tasks.length})</CardTitle></CardHeader><CardContent className="space-y-2">{successor.data.tasks.slice(0, 20).map((task) => <div key={task.id} className="rounded-md border border-border p-3"><div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{task.title}</p><Badge variant={task.priority === "high" ? "danger" : "secondary"}>{task.priority}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{task.description}</p>{task.evidence.map((ev, index) => ev.url ? <a key={index} className="mt-2 inline-block text-[10px] text-primary underline" href={ev.url} target="_blank" rel="noreferrer">{ev.label ?? "Open evidence"}</a> : null)}</div>)}</CardContent></Card><Card><CardHeader><CardTitle className="text-sm">Onboarding path</CardTitle></CardHeader><CardContent className="space-y-3">{successor.data.onboarding.map((step) => { const verified = verification.data?.some((item) => item.status === "verified" && item.result === `Successor confirmed completion of: ${step.title}`); return <div key={step.phase} className="border-l-2 border-primary/40 pl-3"><div className="flex items-center justify-between gap-2"><p className="text-xs font-medium">{step.title}</p>{savedSuccessorPackage ? <Button size="sm" variant="ghost" disabled={verified} onClick={() => void verifyOnboardingStep(step)}>{verified ? "Confirmed" : "Confirm"}</Button> : null}</div><p className="mt-1 text-xs text-muted-foreground">{step.objective}</p></div>; })}</CardContent></Card></div>
                  <p className="text-[11px] text-muted-foreground">{successor.data.limitations.join(" ")}</p>
                </> : null}
              </div>
            </TabsContent>

            <TabsContent value="versions">
              {versions.isLoading ? (
                <Skeleton className="h-40 w-full rounded-lg" />
              ) : (
                <VersionHistory
                  projectId={projectId}
                  handover={document}
                  versions={versions.data ?? []}
                  claimMap={claimMap}
                />
              )}
            </TabsContent>

            {publishedVersion ? (
              <TabsContent value="successor">
                <div className="space-y-4">
                  <div className="panel flex items-center gap-2 border border-status-ok/35 bg-status-ok/[0.06] p-4 text-xs text-muted-foreground">
                    <CheckCircle2 className="h-3.5 w-3.5 text-status-ok" />
                    This is the published handover a successor reads. It is a frozen, human-approved
                    record — it is not regenerated from model output on each view.
                  </div>
                  <VersionDocument
                    projectId={projectId}
                    version={publishedVersion}
                    claimMap={claimMap}
                  />
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void downloadHandover(
                          projectId,
                          document.id,
                          "md",
                          `handover-published-v${publishedVersion.version_number}.md`,
                          publishedVersion.version_number,
                        )
                      }
                    >
                      <FileText className="h-3.5 w-3.5" />
                      Download Markdown
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        void downloadHandover(
                          projectId,
                          document.id,
                          "pdf",
                          `handover-published-v${publishedVersion.version_number}.pdf`,
                          publishedVersion.version_number,
                        )
                      }
                    >
                      <FileDown className="h-3.5 w-3.5" />
                      Download PDF
                    </Button>
                  </div>
                </div>
              </TabsContent>
            ) : null}
          </Tabs>
        </div>
      ) : (
        <EmptyState
          icon={<CircleDashed className="h-4 w-4" />}
          title="Nothing to show"
          description="No handover is available for this project."
        />
      )}
    </div>
  );
}
