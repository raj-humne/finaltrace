import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "@/state/auth";
import { AppShell } from "@/components/shared/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { QueuePage } from "@/pages/QueuePage";
import { IncidentPage } from "@/pages/IncidentPage";
import { UsersPage } from "@/pages/UsersPage";
import { UserPage } from "@/pages/UserPage";
import { DetectionHealthPage } from "@/pages/DetectionHealthPage";

function Protected({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <div className="flex min-h-screen items-center justify-center text-sm text-(--color-ink-muted)">Loading…</div>;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/incidents" replace />} />
      <Route path="/incidents" element={<Protected><QueuePage /></Protected>} />
      <Route path="/incidents/:incidentId" element={<Protected><IncidentPage /></Protected>} />
      <Route path="/users" element={<Protected><UsersPage /></Protected>} />
      <Route path="/users/:userId" element={<Protected><UserPage /></Protected>} />
      <Route path="/detection/health" element={<Protected><DetectionHealthPage /></Protected>} />
      <Route path="*" element={<Navigate to="/incidents" replace />} />
    </Routes>
  );
}
