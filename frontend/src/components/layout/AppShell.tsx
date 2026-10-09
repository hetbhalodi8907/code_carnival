import { Outlet } from "react-router";

import { SideNav } from "@/components/layout/SideNav";
import { TopBar } from "@/components/layout/TopBar";
import { useAuth } from "@/context/useAuth";

export function AppShell() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="flex h-full flex-col">
      <TopBar user={user} onLogout={logout} />
      <div className="flex min-h-0 flex-1">
        <SideNav user={user} />
        <main id="main" className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
