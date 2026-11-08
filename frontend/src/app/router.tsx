import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { ProtectedRoute } from "@/routes/guards";

import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import Projects from "@/pages/Projects";
import ProjectCreate from "@/pages/ProjectCreate";
import ProjectDetails from "@/pages/ProjectDetails";
import Sources from "@/pages/Sources";
import SourceLibrary from "@/pages/SourceLibrary";
import SourceDetails from "@/pages/SourceDetails";
import UploadSources from "@/pages/UploadSources";
import GitHubRepositories from "@/pages/GitHubRepositories";
import NotFound from "@/pages/NotFound";
import Settings from "@/pages/Settings";
import { MemoryLayout } from "@/components/intelligence/MemoryLayout";
import ProjectMemory from "@/pages/ProjectMemory";
import ClaimsExplorer from "@/pages/ClaimsExplorer";
import ClaimDetailPage from "@/pages/ClaimDetailPage";
import ConflictCentre from "@/pages/ConflictCentre";
import UncertaintyCentre from "@/pages/UncertaintyCentre";
import DecisionTimeline from "@/pages/DecisionTimeline";
import HandoverPreview from "@/pages/HandoverPreview";
import ReviewQueue from "@/pages/ReviewQueue";
import AuditTrail from "@/pages/AuditTrail";
import HandoverReadiness from "@/pages/HandoverReadiness";
import SuccessorWorkspace from "@/pages/SuccessorWorkspace";
import KnowledgeRisk from "@/pages/KnowledgeRisk";
import SuccessorChecklist from "@/pages/SuccessorChecklist";
import EvaluationDashboard from "@/pages/EvaluationDashboard";
import SystemHealth from "@/pages/SystemHealth";

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
    <Routes>
      {/* Login and signup redirects: completely removes login barrier for judges */}
      <Route path="/login" element={<Navigate to="/dashboard" replace />} />
      <Route path="/signup" element={<Navigate to="/dashboard" replace />} />

      {/* Optional marketing landing kept at /landing; root / directly opens Continuum */}
      <Route path="/landing" element={<Landing />} />

      {/* All application routes open directly inside AppShell with no sign-in required */}
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/dashboard" element={<Dashboard />} />

        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/new" element={<ProjectCreate />} />
        <Route path="/projects/:projectId" element={<ProjectDetails />} />
        <Route path="/projects/:projectId/sources" element={<SourceLibrary />} />
        <Route path="/projects/:projectId/sources/upload" element={<UploadSources />} />
        <Route path="/projects/:projectId/sources/github" element={<GitHubRepositories />} />

        {/* Shortcuts for direct routes requested in judge access specifications */}
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

        <Route path="/projects/:projectId/memory" element={<MemoryLayout />}>
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
  );
}
