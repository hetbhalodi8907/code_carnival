import { LogOut, Lock } from "lucide-react";
import { useMemo, type ReactNode } from "react";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/context/useAuth";
import { formatPermission } from "@/lib/format";
import { roleIcon, roleLabel } from "@/lib/roles";
import { loadSession } from "@/services/session";

function InfoItem({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-[3px]">
      <dt className="text-[11.5px] uppercase tracking-[0.04em] text-subtle">{label}</dt>
      <dd className={mono ? "break-words font-mono text-[13px]" : "break-words text-sm"}>{children}</dd>
    </div>
  );
}

/** Read-only view of what the server reports for the signed-in account. */
export function ProfilePage() {
  const { user, logout } = useAuth();
  // The token's own expiry, as issued by the server at login. Nothing is invented here.
  const expiresAt = useMemo(() => loadSession()?.expiresAt ?? null, []);
  if (!user) return null;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      <div className="mx-auto flex max-w-[1080px] flex-col gap-[18px] p-4 sm:p-5 lg:p-6">
        <Card>
          <div className="flex flex-col items-start gap-4 p-5 sm:flex-row sm:items-center sm:gap-[18px] sm:p-[22px]">
            <Avatar name={user.full_name} size="lg" />
            <div className="min-w-0 flex-1">
              <h2 className="text-xl font-semibold">{user.full_name}</h2>
              <p className="mt-0.5 break-all font-mono text-[13.5px] text-muted-foreground">{user.email}</p>
              <ul className="mt-2.5 flex flex-wrap gap-2" aria-label="Roles">
                {user.roles.map((role) => {
                  const Icon = roleIcon(role);
                  return (
                    <li key={role}>
                      <Badge>
                        <Icon aria-hidden="true" />
                        {roleLabel(role)}
                      </Badge>
                    </li>
                  );
                })}
                <li>
                  <Badge variant="success">
                    <Lock aria-hidden="true" />
                    Authenticated
                  </Badge>
                </li>
              </ul>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Session &amp; authentication</CardTitle>
            <CardDescription>Current sign-in context for this browser tab.</CardDescription>
          </CardHeader>
          <CardContent className="px-[22px] py-[18px]">
            <dl className="grid gap-x-7 gap-y-4 sm:grid-cols-2">
              <InfoItem label="Account name">{user.full_name}</InfoItem>
              <InfoItem label="Sign-in email" mono>
                {user.email}
              </InfoItem>
              <InfoItem label="Roles">{user.roles.length ? user.roles.map(roleLabel).join(", ") : "No role assigned"}</InfoItem>
              <InfoItem label="Authentication">Bearer token, verified by the Nexora server</InfoItem>
              {expiresAt ? (
                <InfoItem label="Session expires">
                  {new Date(expiresAt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
                </InfoItem>
              ) : null}
              <InfoItem label="Session status">Active</InfoItem>
            </dl>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Access permissions</CardTitle>
            <CardDescription>Permissions the server reports for your account.</CardDescription>
          </CardHeader>
          <CardContent className="px-[22px] py-[18px]">
            {user.permissions.length ? (
              <ul className="flex flex-wrap gap-2" aria-label="Permissions">
                {user.permissions.map((permission) => (
                  <li key={permission}>
                    <Badge className="font-mono text-[11.5px]">{formatPermission(permission)}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No permissions are assigned to this account.</p>
            )}
            <p className="mt-4 flex items-start gap-2 border-t border-border pt-3 text-[12.5px] leading-normal text-subtle">
              <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>
                Document access is granted to roles or individual users by an administrator and enforced by the server
                during retrieval. This page only displays your access; it cannot change or expand it.
              </span>
            </p>
          </CardContent>
        </Card>

        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 px-[22px] py-4">
            <p className="max-w-[60ch] text-[12.5px] text-muted-foreground">
              Logging out ends this session and returns you to the sign-in screen. Tokens and session secrets are never
              displayed here.
            </p>
            <Button variant="danger" onClick={logout}>
              <LogOut aria-hidden="true" />
              Log out
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
