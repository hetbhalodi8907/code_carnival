import { BadgeCheck, KeyRound, Mail, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/context/useAuth";
import { formatPermission, initials } from "@/lib/format";
import { roleAppearance, roleLabel } from "@/lib/roles";

/** Read-only view of what the server reports for the signed-in account. */
export function ProfilePage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto w-full max-w-3xl space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Profile</h1>
          <p className="text-sm text-muted-foreground">Your identity and access as reported by the Nexora server.</p>
        </div>

        <Card className="animate-fade-up">
          <CardContent className="flex flex-col gap-5 p-6 sm:flex-row sm:items-center">
            <div className="grid size-16 shrink-0 place-items-center rounded-2xl border border-primary/30 bg-primary/15 text-xl font-semibold text-primary">
              {initials(user.full_name)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold">{user.full_name}</span>
                <Badge variant="success">
                  <BadgeCheck aria-hidden="true" />
                  Authenticated
                </Badge>
              </div>
              <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                <Mail className="size-4" aria-hidden="true" />
                <span className="truncate">{user.email}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {user.roles.map((role) => {
                  const { icon: Icon, tone } = roleAppearance(role);
                  return (
                    <Badge key={role} className={tone}>
                      <Icon aria-hidden="true" />
                      {roleLabel(role)}
                    </Badge>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="animate-fade-up">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-[15px]">
              <KeyRound className="size-4 text-primary" aria-hidden="true" />
              Permissions
            </CardTitle>
            <CardDescription>Granted through your role and enforced by the server on every request.</CardDescription>
          </CardHeader>
          <CardContent>
            {user.permissions.length ? (
              <ul className="flex flex-wrap gap-2">
                {user.permissions.map((permission) => (
                  <li key={permission}>
                    <Badge variant="muted" className="font-mono text-[11px]">
                      {formatPermission(permission)}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No permissions are assigned to this account.</p>
            )}
          </CardContent>
        </Card>

        <div className="flex gap-3 rounded-xl border border-success/20 bg-success/5 p-4 text-sm">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          <p className="text-muted-foreground">
            Document access is granted explicitly to roles or individual users by an administrator. This page only
            displays your access; it cannot change it.
          </p>
        </div>
      </div>
    </div>
  );
}
