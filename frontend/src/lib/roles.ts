/**
 * Display names and visuals for backend role codes. Presentation only: the roles a
 * user holds always come from GET /api/v1/auth/me and are never decided here.
 */

import { Code2, Crown, Landmark, ShieldCheck, UserRound, Users, type LucideIcon } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "CEO / Super Admin",
  HR_MANAGER: "HR Manager",
  FINANCE_MANAGER: "Finance Manager",
  ENGINEERING_MANAGER: "Engineering Manager",
  SECURITY_MANAGER: "Security Manager",
  EMPLOYEE: "Employee",
};

/** "FINANCE_MANAGER" -> "Finance Manager"; unknown codes are title-cased. */
export function roleLabel(role: string): string {
  return (
    ROLE_LABELS[role] ??
    role
      .toLowerCase()
      .split("_")
      .filter(Boolean)
      .map((word) => word[0].toUpperCase() + word.slice(1))
      .join(" ")
  );
}

/** The role shown in compact UI; the backend returns roles sorted. */
export function primaryRoleLabel(roles: readonly string[]): string {
  return roles.length ? roleLabel(roles[0]) : "No role assigned";
}

export interface RoleAppearance {
  icon: LucideIcon;
  /** Icon tile / badge colours. */
  tone: string;
  /** Border and ring used when a demo card is selected. */
  selected: string;
}

const ROLE_APPEARANCE: Record<string, RoleAppearance> = {
  SUPER_ADMIN: {
    icon: Crown,
    tone: "bg-violet-500/12 text-violet-700 dark:text-violet-300",
    selected: "border-violet-500/60 ring-2 ring-violet-500/25",
  },
  HR_MANAGER: {
    icon: Users,
    tone: "bg-pink-500/12 text-pink-700 dark:text-pink-300",
    selected: "border-pink-500/60 ring-2 ring-pink-500/25",
  },
  FINANCE_MANAGER: {
    icon: Landmark,
    tone: "bg-cyan-500/12 text-cyan-700 dark:text-cyan-300",
    selected: "border-cyan-500/60 ring-2 ring-cyan-500/25",
  },
  ENGINEERING_MANAGER: {
    icon: Code2,
    tone: "bg-blue-500/12 text-blue-700 dark:text-blue-300",
    selected: "border-blue-500/60 ring-2 ring-blue-500/25",
  },
  SECURITY_MANAGER: {
    icon: ShieldCheck,
    tone: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
    selected: "border-emerald-500/60 ring-2 ring-emerald-500/25",
  },
  EMPLOYEE: {
    icon: UserRound,
    tone: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
    selected: "border-slate-400/60 ring-2 ring-slate-400/25",
  },
};

const DEFAULT_APPEARANCE: RoleAppearance = {
  icon: UserRound,
  tone: "bg-primary/12 text-primary",
  selected: "border-primary/60 ring-2 ring-primary/25",
};

export function roleAppearance(role: string | undefined): RoleAppearance {
  return (role && ROLE_APPEARANCE[role]) || DEFAULT_APPEARANCE;
}
