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
import ComingSoon from "@/pages/ComingSoon";
import Settings from "@/pages/Settings";

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

        <Route path="/sources" element={<Sources />} />
        <Route path="/sources/:sourceId" element={<SourceDetails />} />

        <Route
          path="/memory"
          element={
            <ComingSoon
              eyebrow="Later phase"
              title="Knowledge Memory"
              description="Claims, evidence and conflicts will live here once extraction is implemented. Nothing on this page is generated from your sources."
            />
          }
        />
        <Route
          path="/handovers"
          element={
            <ComingSoon
              eyebrow="Later phase"
              title="Handovers"
              description="Handover briefs will be assembled from reviewed claims. This screen is a prepared interface, not a generated document."
            />
          }
        />
        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
