import { Link } from "react-router";

import { Avatar } from "@/components/ui/avatar";
import { roleLabel } from "@/lib/roles";
import type { CurrentUser } from "@/types/api";

/** The authenticated identity, exactly as GET /api/v1/auth/me returned it. Display only. */
export function SessionCard({ user, onNavigate }: { user: CurrentUser; onNavigate?: () => void }) {
  const count = user.permissions.length;
  return (
    <section className="px-2 pb-2.5" aria-label="Signed-in account" data-testid="session-card">
      <div className="flex min-w-0 items-center gap-2.5">
        <Avatar name={user.full_name} />
        <div className="min-w-0 leading-tight">
          <div className="truncate text-[13.5px] font-semibold" data-testid="current-user-name">
            {user.full_name}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {user.roles.length ? user.roles.map(roleLabel).join(", ") : "No role assigned"}
          </div>
        </div>
      </div>
      <div className="mt-2 truncate font-mono text-[11.5px] text-subtle" data-testid="session-email">
        {user.email}
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs">
        <span className="inline-flex items-center gap-1.5 font-semibold text-success-strong" data-testid="auth-state">
          <span className="size-[7px] rounded-full bg-success" aria-hidden="true" />
          Authenticated
        </span>
        <Link to="/app/profile" onClick={onNavigate} className="text-muted-foreground hover:text-foreground">
          {count} server-granted {count === 1 ? "permission" : "permissions"}
        </Link>
      </div>
    </section>
  );
}
