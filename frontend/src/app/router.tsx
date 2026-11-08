import { Route, Routes } from "react-router-dom";

import { ProtectedRoute, PublicOnlyRoute } from "@/routes/guards";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
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

/**
 * Every authenticated screen renders inside the AppShell via ProtectedRoute,
 * which also performs the client-side session gate. The backend re-checks
 * membership on every request, so this gate is a UX affordance only.
 */
export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        path="/login"
        element={
          <PublicOnlyRoute>
            <Login />
          </PublicOnlyRoute>
        }
      />

      <Route element={<ProtectedRoute />}>
        <Route path="/dashboard" element={<Dashboard />} />

        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/new" element={<ProjectCreate />} />
        <Route path="/projects/:projectId" element={<ProjectDetails />} />
        <Route path="/projects/:projectId/sources" element={<SourceLibrary />} />
        <Route path="/projects/:projectId/sources/upload" element={<UploadSources />} />
        <Route path="/projects/:projectId/sources/github" element={<GitHubRepositories />} />

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
        <Route path="/projects/:projectId/audit" element={<AuditTrail />} />

        <Route path="/sources" element={<Sources />} />
        <Route path="/sources/:sourceId" element={<SourceDetails />} />

        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
