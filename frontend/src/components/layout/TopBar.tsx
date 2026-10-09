import { Menu } from "lucide-react";
import type { RefObject } from "react";

import { SessionPill } from "@/components/layout/SessionPill";
import { UserMenu } from "@/components/layout/UserMenu";
import { Button } from "@/components/ui/button";
import { primaryRoleLabel } from "@/lib/roles";
import type { CurrentUser } from "@/types/api";

interface TopBarProps {
  user: CurrentUser;
  title: string;
  crumb: string;
  onLogout: () => void;
  onOpenNavigation: () => void;
  navigationId: string;
  navigationOpen: boolean;
  menuButtonRef: RefObject<HTMLButtonElement | null>;
}

export function TopBar({ user, title, crumb, onLogout, onOpenNavigation, navigationId, navigationOpen, menuButtonRef }: TopBarProps) {
  return (
    <header className="flex h-[60px] shrink-0 items-center gap-2 border-b border-border bg-card px-3 sm:gap-3 sm:px-5">
      <Button
        ref={menuButtonRef}
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onOpenNavigation}
        aria-label="Open navigation"
        aria-controls={navigationId}
        aria-expanded={navigationOpen}
      >
        <Menu aria-hidden="true" />
      </Button>
      <div className="flex min-w-0 flex-col">
        <h1 className="truncate text-base font-semibold">{title}</h1>
        <span className="hidden text-xs text-subtle sm:block">{crumb}</span>
      </div>
      <div className="ml-auto flex items-center gap-2.5">
        <SessionPill />
        <span
          className="hidden h-[30px] items-center rounded-full border border-border bg-muted px-2.5 text-xs font-semibold text-muted-foreground sm:inline-flex"
          data-testid="current-user-role"
        >
          {primaryRoleLabel(user.roles)}
        </span>
        <UserMenu user={user} onLogout={onLogout} />
      </div>
    </header>
  );
}
