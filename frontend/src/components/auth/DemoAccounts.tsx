import { ArrowRight, Check, FlaskConical } from "lucide-react";

import { DEMO_ACCOUNTS, type DemoAccount } from "@/config/demoAccounts";
import { roleAppearance, roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";

interface DemoAccountsProps {
  selected: DemoAccount | null;
  onSelect: (account: DemoAccount) => void;
}

function ActionPill({ selected, className }: { selected: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors",
        selected
          ? "bg-success/15 text-success"
          : "bg-primary/12 text-primary group-hover:bg-primary group-hover:text-primary-foreground",
        className,
      )}
    >
      {selected ? "Selected" : "Use demo account"}
      {selected ? <Check className="size-3.5" aria-hidden="true" /> : <ArrowRight className="size-3.5" aria-hidden="true" />}
    </span>
  );
}

/** Clickable demo-account cards. Selecting one only fills the login form. */
export function DemoAccounts({ selected, onSelect }: DemoAccountsProps) {
  return (
    <section aria-labelledby="demo-accounts-heading" className="animate-fade-up">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.18em] text-primary">
            <FlaskConical className="size-3.5" aria-hidden="true" />
            Hackathon demo accounts
          </p>
          <h2 id="demo-accounts-heading" className="mt-1.5 text-2xl font-semibold tracking-tight">
            Demo Accounts
          </h2>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            Pick a role to fill the login form, then log in. Each account sees only what the server authorizes
            for that role.
          </p>
        </div>
        <span className="rounded-full border border-warning/30 bg-warning/10 px-3 py-1 text-xs font-medium text-warning">
          Local demo credentials · not for production
        </span>
      </div>

      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {DEMO_ACCOUNTS.map((account) => {
          const { icon: Icon, tone, selected: selectedStyle } = roleAppearance(account.role);
          const isSelected = selected?.email === account.email;
          return (
            <li key={account.email}>
              <button
                type="button"
                onClick={() => onSelect(account)}
                aria-pressed={isSelected}
                data-testid={`demo-account-${account.role}`}
                className={cn(
                  "group flex h-full w-full flex-col rounded-xl border bg-card/80 p-3.5 text-left outline-none transition-[border-color,box-shadow,background-color,transform]",
                  "hover:-translate-y-0.5 hover:border-primary/40 hover:bg-card focus-visible:ring-2 focus-visible:ring-ring",
                  isSelected ? selectedStyle : "border-border",
                )}
              >
                <span className="flex items-start gap-3">
                  <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", tone)}>
                    <Icon className="size-5" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold leading-tight">{roleLabel(account.role)}</span>
                    <span className="block text-sm text-muted-foreground">{account.name}</span>
                  </span>
                  <ActionPill selected={isSelected} className="hidden sm:inline-flex" />
                </span>

                <span className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 rounded-lg bg-background/60 px-3 py-2 font-mono text-[12px]">
                  <span className="text-muted-foreground">Email</span>
                  <span className="truncate">{account.email}</span>
                  <span className="text-muted-foreground">Password</span>
                  <span className="truncate">{account.password}</span>
                </span>

                <span className="mt-2.5 block flex-1 text-xs leading-relaxed text-muted-foreground">
                  {account.description}
                </span>

                <ActionPill selected={isSelected} className="mt-3 inline-flex self-start sm:hidden" />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
