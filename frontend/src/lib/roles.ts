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

const ROLE_ICONS: Record<string, LucideIcon> = {
  SUPER_ADMIN: Crown,
  HR_MANAGER: Users,
  FINANCE_MANAGER: Landmark,
  ENGINEERING_MANAGER: Code2,
  SECURITY_MANAGER: ShieldCheck,
  EMPLOYEE: UserRound,
};

export function roleIcon(role: string | undefined): LucideIcon {
  return (role && ROLE_ICONS[role]) || UserRound;
}
