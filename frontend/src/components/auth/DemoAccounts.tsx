import { ArrowRight, Check, Info } from "lucide-react";

import { DEMO_ACCOUNTS, type DemoAccount } from "@/config/demoAccounts";
import { roleIcon, roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";

interface DemoAccountsProps {
  selected: DemoAccount | null;
  onSelect: (account: DemoAccount) => void;
}

/**
 * Clickable demo-account cards from config/demoAccounts.ts. Selecting one only fills the
 * login form; the real login call and the server decide everything else.
 */
export function DemoAccounts({ selected, onSelect }: DemoAccountsProps) {
  return (
    <section aria-labelledby="demo-accounts-heading" className="flex min-w-0 flex-col">
      <div className="mb-4">
        <h2 id="demo-accounts-heading" className="text-[15px] font-semibold tracking-[0.01em]">
          Hackathon Demo Accounts
        </h2>
        <p className="mt-1 max-w-[62ch] text-[13px] text-muted-foreground">
          Select a role to fill the login form, then log in. Each role sees only the sources the server authorizes
          for it.
        </p>
      </div>

      <ul className="grid content-start gap-3 sm:grid-cols-2">
        {DEMO_ACCOUNTS.map((account) => {
          const Icon = roleIcon(account.role);
          const isSelected = selected?.email === account.email;
          return (
            <li key={account.email}>
              <button
                type="button"
                onClick={() => onSelect(account)}
                aria-pressed={isSelected}
                data-testid={`demo-account-${account.role}`}
                className={cn(
                  "grid h-full w-full grid-cols-[auto_1fr] gap-3 rounded-xl border bg-card p-3.5 text-left transition-[border-color,box-shadow,background-color]",
                  isSelected
                    ? "border-primary bg-primary-soft ring-[3px] ring-ring"
                    : "border-border hover:border-border-strong hover:shadow-sm",
                )}
              >
                <span
                  className={cn(
                    "inline-flex size-[38px] items-center justify-center rounded-[9px] border",
                    isSelected ? "border-primary bg-primary text-white" : "border-border bg-muted text-muted-foreground",
                  )}
                >
                  <Icon className="size-5" aria-hidden="true" />
                </span>
                <span className="flex min-w-0 flex-col gap-[3px]">
                  <span className="text-sm font-semibold">{roleLabel(account.role)}</span>
                  <span className="text-[12.5px] leading-snug text-muted-foreground">{account.description}</span>
                  <span className="truncate font-mono text-[11.5px] text-subtle">{account.email}</span>
                </span>
                <span className="col-span-2 mt-0.5 flex items-center justify-between border-t border-dashed border-border pt-2 text-[12.5px] font-semibold text-primary">
                  {isSelected ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Check className="size-3.5" aria-hidden="true" />
                      Selected
                    </span>
                  ) : (
                    <>
                      <span>Use demo account</span>
                      <ArrowRight className="size-3.5" aria-hidden="true" />
                    </>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <p className="mt-4 flex items-start gap-2 rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-[12.5px] leading-normal text-muted-foreground">
        <Info className="mt-px size-4 shrink-0 text-subtle" aria-hidden="true" />
        <span>
          <strong className="font-semibold">Local demo credentials · not for production</strong>
          {" "}— pre-seeded for this hackathon build. They open synthetic sample documents for the fictional Nexora
          Technologies, not real company data.
        </span>
      </p>
    </section>
  );
}
