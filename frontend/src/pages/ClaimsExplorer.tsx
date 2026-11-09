import * as React from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { FilterX, Search, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState, ErrorState } from "@/components/common/States";
import { TableSkeleton } from "@/components/common/PageHeader";
import { ClaimCard } from "@/components/intelligence/ClaimCard";
import { useClaims, useProjectMemory } from "@/hooks/use-memory";
import { usePageTitle } from "@/hooks/use-page-title";
import { CLAIM_STATUS_META, CLAIM_TYPE_META, CLAIM_TYPE_ORDER } from "@/lib/intelligence-meta";
import type { ClaimListParams, ClaimStatus, ClaimType } from "@/types";

const PAGE_SIZE = 20;
const ALL = "__all__";

function parseParams(search: URLSearchParams): ClaimListParams {
  const page = Number(search.get("page") ?? "1");
  return {
    category: (search.get("category") as ClaimType) || undefined,
    status: (search.get("status") as ClaimStatus) || undefined,
    critical: search.get("critical") === "true" ? true : undefined,
    search: search.get("search") || undefined,
    order: (search.get("order") as ClaimListParams["order"]) || "recent",
    page: Number.isFinite(page) && page > 0 ? page : 1,
    page_size: PAGE_SIZE,
  };
}

export default function ClaimsExplorer() {
  const { projectId } = useParams<{ projectId: string }>();
  usePageTitle("Claims Explorer");
  const [searchParams, setSearchParams] = useSearchParams();
  const params = React.useMemo(() => parseParams(searchParams), [searchParams]);
  const [searchInput, setSearchInput] = React.useState(params.search ?? "");

  const claims = useClaims(projectId, params);
  const memory = useProjectMemory(projectId);

  // Keep the text box in sync when the URL changes (e.g. back/forward).
  React.useEffect(() => {
    setSearchInput(params.search ?? "");
  }, [params.search]);

  const update = (patch: Record<string, string | null>, resetPage = true) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    if (resetPage) next.delete("page");
    setSearchParams(next, { replace: true });
  };

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    update({ search: searchInput.trim() || null });
  };

  const clearFilters = () => setSearchParams(new URLSearchParams(), { replace: true });

  const filtersActive =
    Boolean(params.category || params.status || params.critical || params.search) ||
    (params.order ?? "recent") !== "recent";

  if (!projectId) return null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
          Every claim below was extracted from an authorised source and linked to the passage it
          came from. Status is decided by evidence, not by the model alone.
        </p>
        {memory.data && !memory.data.reconstructed ? (
          <span className="text-[11px] text-muted-foreground">
            No reconstruction has run yet for this project.
          </span>
        ) : null}
      </div>

      <form
        onSubmit={submitSearch}
        className="flex flex-wrap items-end gap-2 rounded-lg border border-border bg-card/40 p-3"
        aria-label="Claim filters"
      >
        <div className="min-w-[180px] flex-1 space-y-1.5">
          <Label htmlFor="claim-search" className="text-[11px] text-muted-foreground">
            Search claim text
          </Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="claim-search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="e.g. webhook retries"
              className="pl-8"
            />
          </div>
        </div>

        <div className="w-[170px] space-y-1.5">
          <Label className="text-[11px] text-muted-foreground">Category</Label>
          <Select
            value={params.category ?? ALL}
            onValueChange={(value) => update({ category: value === ALL ? null : value })}
          >
            <SelectTrigger>
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All categories</SelectItem>
              {CLAIM_TYPE_ORDER.map((type) => (
                <SelectItem key={type} value={type}>
                  {CLAIM_TYPE_META[type].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-[150px] space-y-1.5">
          <Label className="text-[11px] text-muted-foreground">Status</Label>
          <Select
            value={params.status ?? ALL}
            onValueChange={(value) => update({ status: value === ALL ? null : value })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Any status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Any status</SelectItem>
              {(Object.keys(CLAIM_STATUS_META) as ClaimStatus[]).map((status) => (
                <SelectItem key={status} value={status}>
                  {CLAIM_STATUS_META[status].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="w-[140px] space-y-1.5">
          <Label className="text-[11px] text-muted-foreground">Order</Label>
          <Select
            value={params.order ?? "recent"}
            onValueChange={(value) => update({ order: value === "recent" ? null : value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="recent">Newest first</SelectItem>
              <SelectItem value="oldest">Oldest first</SelectItem>
              <SelectItem value="timeline">Source date</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" variant="outline">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Apply
          </Button>
          {filtersActive ? (
            <Button type="button" size="sm" variant="ghost" onClick={clearFilters}>
              <FilterX className="h-3.5 w-3.5" />
              Clear
            </Button>
          ) : null}
        </div>
      </form>

      {claims.isLoading ? (
        <TableSkeleton columns={["Claim", "Status", "Type"]} rows={4} />
      ) : claims.isError ? (
        <ErrorState
          error={claims.error}
          title="Claims could not be loaded"
          onRetry={() => void claims.refetch()}
        />
      ) : !claims.data || claims.data.items.length === 0 ? (
        <EmptyState
          title={filtersActive ? "No claims match these filters" : "No claims yet"}
          description={
            filtersActive
              ? "Try widening the filters or clearing the search."
              : "Run a reconstruction from the Memory overview to extract claims from this project's sources."
          }
          action={
            filtersActive ? (
              <Button size="sm" variant="outline" onClick={clearFilters}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="tabular-nums">
              {claims.data.meta.total} claim{claims.data.meta.total === 1 ? "" : "s"}
            </span>
            {Object.entries(claims.data.status_counts).map(([status, count]) => (
              <span
                key={status}
                className="inline-flex items-center gap-1.5 rounded-md border border-border/70 bg-card/40 px-2 py-0.5"
              >
                {CLAIM_STATUS_META[status as ClaimStatus]?.label ?? status}
                <span className="tabular-nums">{count}</span>
              </span>
            ))}
          </div>

          <div className="space-y-3">
            {claims.data.items.map((claim) => (
              <ClaimCard key={claim.id} projectId={projectId} claim={claim} />
            ))}
          </div>

          {claims.data.meta.total_pages > 1 ? (
            <div className="flex items-center justify-between border-t border-border/70 pt-3">
              <span className="text-[11px] text-muted-foreground">
                Page {claims.data.meta.page} of {claims.data.meta.total_pages}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!claims.data.meta.has_previous}
                  onClick={() => update({ page: String(params.page! - 1) }, false)}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!claims.data.meta.has_next}
                  onClick={() => update({ page: String(params.page! + 1) }, false)}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
