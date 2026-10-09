import { Link } from "react-router";

import { initials } from "@/lib/format";
import { primaryRoleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import type { CurrentUser } from "@/types/api";

/** Who is signed in, exactly as reported by GET /api/v1/auth/me. Links to the profile. */
export function UserBadge({ user, className }: { user: CurrentUser; className?: string }) {
  const role = primaryRoleLabel(user.roles);
  return (
    <Link
      to="/app/profile"
      className={cn(
        "flex items-center gap-3 rounded-lg px-1.5 py-1 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      aria-label={`${user.full_name}, ${role}. View profile`}
    >
      <span className="hidden text-right leading-tight sm:block">
        <span className="block text-sm font-medium" data-testid="current-user-name">
          {user.full_name}
        </span>
        <span className="block text-xs text-primary" data-testid="current-user-role">
          {role}
        </span>
      </span>
      <span
        className="grid size-9 place-items-center rounded-full border border-primary/30 bg-primary/15 text-xs font-semibold text-primary"
        aria-hidden="true"
      >
        {initials(user.full_name)}
      </span>
    </Link>
  );
}
