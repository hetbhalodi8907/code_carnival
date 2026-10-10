import { Navigate, Route, Routes } from "react-router";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { ApprovalQueuePage } from "@/pages/ApprovalQueuePage";
import { ChatPage } from "@/pages/ChatPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ImageUploadPage } from "@/pages/ImageUploadPage";
import { LoginPage } from "@/pages/LoginPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { UploadPage } from "@/pages/UploadPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/app" element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="upload-image" element={<ImageUploadPage />} />
          <Route path="approvals" element={<ApprovalQueuePage />} />
          <Route path="profile" element={<ProfilePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/app/dashboard" replace />} />
    </Routes>
  );
}
