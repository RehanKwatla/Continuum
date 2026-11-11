import * as React from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { ProtectedRoute } from "@/routes/guards";
import { Skeleton } from "@/components/ui/skeleton";

// Eagerly-loaded routes (critical path — dashboard is the judge entry point)
import Dashboard from "@/pages/Dashboard";
import Landing from "@/pages/Landing";
import NotFound from "@/pages/NotFound";

// All other routes are lazy-loaded to split the 979 kB bundle into smaller chunks.
const Projects = React.lazy(() => import("@/pages/Projects"));
const ProjectCreate = React.lazy(() => import("@/pages/ProjectCreate"));
const ProjectDetails = React.lazy(() => import("@/pages/ProjectDetails"));
const Sources = React.lazy(() => import("@/pages/Sources"));
const SourceLibrary = React.lazy(() => import("@/pages/SourceLibrary"));
const SourceDetails = React.lazy(() => import("@/pages/SourceDetails"));
const UploadSources = React.lazy(() => import("@/pages/UploadSources"));
const GitHubRepositories = React.lazy(() => import("@/pages/GitHubRepositories"));
const Settings = React.lazy(() => import("@/pages/Settings"));
const MemoryLayoutLazy = React.lazy(() =>
  import("@/components/intelligence/MemoryLayout").then((m) => ({ default: m.MemoryLayout })),
);
const ProjectMemory = React.lazy(() => import("@/pages/ProjectMemory"));
const ClaimsExplorer = React.lazy(() => import("@/pages/ClaimsExplorer"));
const ClaimDetailPage = React.lazy(() => import("@/pages/ClaimDetailPage"));
const ConflictCentre = React.lazy(() => import("@/pages/ConflictCentre"));
const UncertaintyCentre = React.lazy(() => import("@/pages/UncertaintyCentre"));
const DecisionTimeline = React.lazy(() => import("@/pages/DecisionTimeline"));
const HandoverPreview = React.lazy(() => import("@/pages/HandoverPreview"));
const ReviewQueue = React.lazy(() => import("@/pages/ReviewQueue"));
const AuditTrail = React.lazy(() => import("@/pages/AuditTrail"));
const HandoverReadiness = React.lazy(() => import("@/pages/HandoverReadiness"));
const SuccessorWorkspace = React.lazy(() => import("@/pages/SuccessorWorkspace"));
const KnowledgeRisk = React.lazy(() => import("@/pages/KnowledgeRisk"));
const SuccessorChecklist = React.lazy(() => import("@/pages/SuccessorChecklist"));
const EvaluationDashboard = React.lazy(() => import("@/pages/EvaluationDashboard"));
const SystemHealth = React.lazy(() => import("@/pages/SystemHealth"));

/** Minimal skeleton shown while a lazy route chunk is loading. */
function RouteLoader() {
  return (
    <div className="space-y-4 p-6">
      <Skeleton className="h-8 w-48 rounded" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

/** Deep-link shortcut redirect for project memory subviews. */
function ProjectSubrouteRedirect({ subpath }: { subpath: string }) {
  const { projectId } = useParams();
  return <Navigate to={`/projects/${projectId}/${subpath}`} replace />;
}

/**
 * Public Judge Access Router:
 * - Direct frictionless entry at root `/` and `/dashboard` (no login gate)
 * - Deep link support for all project routes on refresh and incognito browsing
 * - Zero authentication redirects across the judge journey
 */
export function AppRouter() {
  return (
    <React.Suspense fallback={<RouteLoader />}>
      <Routes>
        {/* Login and signup redirects: removes login barrier for judges */}
        <Route path="/login" element={<Navigate to="/dashboard" replace />} />
        <Route path="/signup" element={<Navigate to="/dashboard" replace />} />

        {/* Marketing landing kept at / and /landing */}
        <Route path="/" element={<Landing />} />
        <Route path="/landing" element={<Landing />} />

        {/* All application routes open directly inside AppShell with no sign-in required */}
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />

          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/new" element={<ProjectCreate />} />
          <Route path="/projects/:projectId" element={<ProjectDetails />} />
          <Route path="/projects/:projectId/sources" element={<SourceLibrary />} />
          <Route path="/projects/:projectId/sources/upload" element={<UploadSources />} />
          <Route path="/projects/:projectId/sources/github" element={<GitHubRepositories />} />

          {/* Shortcuts for direct routes */}
          <Route
            path="/projects/:projectId/review"
            element={<ProjectSubrouteRedirect subpath="memory/review" />}
          />
          <Route
            path="/projects/:projectId/conflicts"
            element={<ProjectSubrouteRedirect subpath="memory/conflicts" />}
          />
          <Route
            path="/projects/:projectId/claims"
            element={<ProjectSubrouteRedirect subpath="memory/claims" />}
          />

          <Route path="/projects/:projectId/memory" element={<MemoryLayoutLazy />}>
            <Route index element={<ProjectMemory />} />
            <Route path="review" element={<ReviewQueue />} />
            <Route path="claims" element={<ClaimsExplorer />} />
            <Route path="claims/:claimId" element={<ClaimDetailPage />} />
            <Route path="conflicts" element={<ConflictCentre />} />
            <Route path="uncertainty" element={<UncertaintyCentre />} />
            <Route path="timeline" element={<DecisionTimeline />} />
          </Route>
          <Route path="/projects/:projectId/handover" element={<HandoverPreview />} />
          <Route path="/projects/:projectId/readiness" element={<HandoverReadiness />} />
          <Route path="/projects/:projectId/successor-workspace" element={<SuccessorWorkspace />} />
          <Route path="/projects/:projectId/successor-checklist" element={<SuccessorChecklist />} />
          <Route path="/projects/:projectId/knowledge-risk" element={<KnowledgeRisk />} />
          <Route path="/projects/:projectId/evaluation" element={<EvaluationDashboard />} />
          <Route path="/projects/:projectId/system-health" element={<SystemHealth />} />
          <Route path="/projects/:projectId/audit" element={<AuditTrail />} />

          <Route path="/sources" element={<Sources />} />
          <Route path="/sources/:sourceId" element={<SourceDetails />} />

          <Route path="/settings" element={<Settings />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </React.Suspense>
  );
}
