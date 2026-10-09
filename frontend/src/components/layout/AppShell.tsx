import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router";

import { navItemForPath } from "@/components/layout/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useAuth } from "@/context/useAuth";

/** Signed-in frame: sidebar (a drawer below md), top bar and the routed page. */
export function AppShell() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebarId = useId();
  const page = navItemForPath(pathname);

  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  useEffect(() => {
    if (!drawerOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setDrawerOpen(false);
      menuButton.current?.focus();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  if (!user) return null;
  return (
    <div className="grid h-full grid-cols-1 grid-rows-[minmax(0,1fr)] overflow-hidden md:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar id={sidebarId} user={user} onLogout={logout} open={drawerOpen} onClose={closeDrawer} />
      {drawerOpen ? (
        <div className="fixed inset-0 z-[60] bg-[rgb(16_24_40/0.4)] md:hidden" onClick={closeDrawer} aria-hidden="true" />
      ) : null}
      <div className="flex min-h-0 min-w-0 flex-col">
        <TopBar
          user={user}
          title={page.title}
          crumb={page.crumb}
          onLogout={logout}
          onOpenNavigation={() => setDrawerOpen(true)}
          navigationId={sidebarId}
          navigationOpen={drawerOpen}
          menuButtonRef={menuButton}
        />
        <main id="main" className="flex min-h-0 min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
