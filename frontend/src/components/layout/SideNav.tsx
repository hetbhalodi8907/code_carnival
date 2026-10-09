import { LockKeyhole } from "lucide-react";
import { NavLink } from "react-router";

import { NAV_ITEMS } from "@/components/layout/navigation";
import { SessionCard } from "@/components/layout/SessionCard";
import type { CurrentUser } from "@/types/api";
import { cn } from "@/lib/utils";

export function SideNav({ user }: { user: CurrentUser }) {
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/30 md:flex" aria-label="Primary">
      <nav className="flex flex-col gap-1 p-3">
        <div className="px-3 pb-2 pt-3 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          Workspace
        </div>
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                isActive
                  ? "bg-primary/12 text-foreground shadow-[inset_2px_0_0_var(--primary)]"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )
            }
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-3 pt-2">
        <SessionCard user={user} />
      </div>
      <div className="mt-auto p-4">
        <div className="rounded-xl border border-border bg-background/60 p-4">
          <LockKeyhole className="mb-2 size-4 text-success" aria-hidden="true" />
          <p className="text-xs leading-relaxed text-muted-foreground">
            Unauthorized information never reaches the AI. Access is enforced on the server for every request.
          </p>
        </div>
      </div>
    </aside>
  );
}
