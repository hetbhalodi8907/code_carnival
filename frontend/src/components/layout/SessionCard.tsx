import { ChevronRight } from "lucide-react";
import { Link } from "react-router";

import { roleAppearance, roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import type { CurrentUser } from "@/types/api";

/** The authenticated identity, as returned by the server. Display only. */
export function SessionCard({ user }: { user: CurrentUser }) {
  return (
    <section className="rounded-xl border border-border bg-background/60 p-3.5" aria-label="Signed-in account" data-testid="session-card">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">Signed in</span>
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-success" data-testid="auth-state">
          <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
          Authenticated
        </span>
      </div>
      <div className="mt-2.5 truncate text-sm font-semibold">{user.full_name}</div>
      <div className="text-xs break-all text-muted-foreground" data-testid="session-email">
        {user.email}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Roles">
        {user.roles.map((role) => {
          const { icon: Icon, tone } = roleAppearance(role);
          return (
            <li key={role} className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", tone)}>
              <Icon className="size-3" aria-hidden="true" />
              {roleLabel(role)}
            </li>
          );
        })}
      </ul>
      <Link
        to="/app/profile"
        className="mt-3 flex items-center justify-between rounded-md text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        {user.permissions.length} server-granted permissions
        <ChevronRight className="size-3.5" aria-hidden="true" />
      </Link>
    </section>
  );
}
