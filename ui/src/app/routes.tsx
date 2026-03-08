import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "@/components/shell/AppShell";
import { OverviewPage } from "@/pages/overview";
import { ResumesPage } from "@/pages/resumes";
import { EvidencePage } from "@/pages/evidence";
import { JobsPage } from "@/pages/jobs";
import { QuickRunPage } from "@/pages/quick-run";
import { AgentRunPage } from "@/pages/agent-run";
import { SubmissionsPage } from "@/pages/submissions";
import { PolicyPage } from "@/pages/policy";
import { SystemSettingsPage } from "@/pages/system-settings";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "resumes", element: <ResumesPage /> },
      { path: "evidence", element: <EvidencePage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "quick-run", element: <QuickRunPage /> },
      { path: "agent-run", element: <AgentRunPage /> },
      { path: "submissions", element: <SubmissionsPage /> },
      { path: "policy", element: <PolicyPage /> },
      { path: "system-settings", element: <SystemSettingsPage /> },
    ],
  },
]);
