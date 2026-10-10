import { Lock, LogOut, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { NavLink } from "react-router";

import { NexoraWordmark } from "@/components/brand/NexoraLogo";
import { NAV_ITEMS } from "@/components/layout/navigation";
import { SessionCard } from "@/components/layout/SessionCard";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CurrentUser } from "@/types/api";

interface SidebarProps {
  id: string;
  user: CurrentUser;
  onLogout: () => void;
  /** Mobile drawer state. From the md breakpoint the sidebar is always visible. */
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ id, user, onLogout, open, onClose }: SidebarProps) {
  const closeButton = useRef<HTMLButtonElement>(null);

  // Wait a frame: while the drawer slides in, the browser still treats it as hidden and ignores focus().
  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => closeButton.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  return (
    <aside
      id={id}
      aria-label="Primary"
      className={cn(
        "z-[70] flex min-h-0 w-[280px] flex-col border-r border-border bg-card px-3 py-4",
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:duration-200",
        // Visibility only transitions on close, so the drawer is focusable the moment it opens.
        open
          ? "max-md:visible max-md:translate-x-0 max-md:shadow-md max-md:transition-transform"
          : "max-md:invisible max-md:-translate-x-full max-md:transition-[transform,visibility]",
        "md:static md:w-auto",
      )}
    >
      <div className="flex items-center justify-between px-2 pb-4 pt-1.5">
        <NexoraWordmark compact subtitle="" />
        <Button ref={closeButton} variant="ghost" size="icon" className="md:hidden" onClick={onClose} aria-label="Close navigation">
          <X aria-hidden="true" />
        </Button>
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto" aria-label="Sections">
        {NAV_ITEMS.filter((item) => !item.onlyWith || user.permissions.includes(item.onlyWith)).map(({ to, label, icon: Icon, requires }) => {
          const locked = Boolean(requires) && !user.permissions.includes(requires as string);
          return (
            <NavLink
              key={to}
              to={to}
              onClick={onClose}
              title={locked ? `Requires the ${requires} permission` : undefined}
              className={({ isActive }) =>
                cn(
                  "relative flex items-center gap-2.5 rounded-lg px-2.5 py-[9px] text-sm transition-colors",
                  isActive
                    ? "bg-primary-soft font-semibold text-primary before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-r-full before:bg-primary"
                    : "font-medium text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <Icon className="size-[18px]" aria-hidden="true" />
              {label}
              {locked ? (
                <>
                  <Lock className="ml-auto size-3.5 shrink-0 opacity-70" aria-hidden="true" />
                  <span className="sr-only">(locked: requires the {requires} permission)</span>
                </>
              ) : null}
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-2 flex flex-col gap-1.5 border-t border-border pt-3">
        <SessionCard user={user} onNavigate={onClose} />
        <Button
          variant="ghost"
          className="h-[38px] w-full justify-start px-2.5 font-medium hover:bg-destructive-soft hover:text-destructive"
          onClick={onLogout}
        >
          <LogOut aria-hidden="true" />
          Log out
        </Button>
      </div>
    </aside>
  );
}
