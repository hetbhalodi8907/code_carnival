import { LogOut, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { Avatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import type { CurrentUser } from "@/types/api";

const ITEM =
  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-[9px] text-left text-[13.5px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground [&_svg]:size-4 [&_svg]:text-subtle";

/** Account dropdown in the top bar: who is signed in, a link to the profile, and Log out. */
export function UserMenu({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={container} className="relative">
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        className={cn("grid size-9 place-items-center rounded-lg hover:bg-muted", open && "bg-muted")}
      >
        <Avatar name={user.full_name} size="sm" />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 top-[calc(100%+8px)] z-50 min-w-[232px] rounded-xl border border-border bg-card p-1.5 shadow-md"
        >
          <div className="mb-1 border-b border-border px-2.5 pb-2 pt-2.5">
            <span className="block truncate text-[13.5px] font-semibold">{user.full_name}</span>
            <span className="block truncate font-mono text-xs text-subtle">{user.email}</span>
          </div>
          <button
            type="button"
            role="menuitem"
            className={ITEM}
            onClick={() => {
              setOpen(false);
              navigate("/app/profile");
            }}
          >
            <UserRound aria-hidden="true" />
            View profile
          </button>
          <button
            type="button"
            role="menuitem"
            className={cn(ITEM, "text-destructive hover:bg-destructive-soft hover:text-destructive [&_svg]:text-destructive")}
            onClick={onLogout}
          >
            <LogOut aria-hidden="true" />
            Log out
          </button>
        </div>
      ) : null}
    </div>
  );
}
