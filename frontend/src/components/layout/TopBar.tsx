import { LogOut } from "lucide-react";
import { NavLink } from "react-router";

import { NexoraWordmark } from "@/components/brand/NexoraLogo";
import { NAV_ITEMS } from "@/components/layout/navigation";
import { SecureModeIndicator } from "@/components/layout/SecureModeIndicator";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { UserBadge } from "@/components/layout/UserBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CurrentUser } from "@/types/api";

export function TopBar({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/65 sm:px-6">
      <NexoraWordmark subtitle="Secure AI Workspace" textClassName="hidden sm:block" />

      <nav className="ml-1 flex items-center gap-1 md:hidden" aria-label="Primary">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            aria-label={label}
            title={label}
            className={({ isActive }) =>
              cn(
                "grid size-9 place-items-center rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring",
                isActive ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent",
              )
            }
          >
            <Icon className="size-4" aria-hidden="true" />
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <SecureModeIndicator />
        <div className="mx-1 hidden h-6 w-px bg-border sm:block" aria-hidden="true" />
        <UserBadge user={user} />
        <ThemeToggle />
        <Button variant="outline" size="sm" onClick={onLogout} className="h-9 px-2.5 sm:px-3">
          <LogOut aria-hidden="true" />
          <span className="sr-only sm:not-sr-only">Log out</span>
        </Button>
      </div>
    </header>
  );
}
