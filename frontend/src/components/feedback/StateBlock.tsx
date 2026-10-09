import { Info, Lock, type LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

const TONES = {
  neutral: "border-border bg-muted text-muted-foreground",
  info: "border-primary/20 bg-primary-soft text-primary",
  success: "border-success/25 bg-success-soft text-success",
  warning: "border-warning/30 bg-warning-soft text-warning",
  error: "border-destructive/25 bg-destructive-soft text-destructive",
};

interface StateBlockProps extends Omit<ComponentProps<"div">, "title"> {
  icon: LucideIcon;
  tone: keyof typeof TONES;
  /** Small label above the title, e.g. "No results". */
  tag?: string;
  title: string;
  actions?: ReactNode;
  /** A quiet footnote under a divider. */
  hint?: string;
  hintIcon?: "lock" | "info";
}

/** A titled status card for an assistant outcome that is not an answer (no results, errors, outages). */
export function StateBlock({ icon: Icon, tone, tag, title, actions, hint, hintIcon = "lock", children, className, ...props }: StateBlockProps) {
  const HintIcon = hintIcon === "lock" ? Lock : Info;
  return (
    <div className={cn("rounded-xl border border-border bg-card p-5 shadow-xs", className)} {...props}>
      <div className="flex items-start gap-3">
        <span className={cn("inline-flex size-[34px] shrink-0 items-center justify-center rounded-[9px] border", TONES[tone])}>
          <Icon className="size-[18px]" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          {tag ? (
            <span className="inline-block rounded-[5px] bg-muted px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.04em] text-muted-foreground">
              {tag}
            </span>
          ) : null}
          <h3 className={cn("text-[15px] font-semibold", tag && "mt-2")}>{title}</h3>
          <p className="mt-1 text-[13.5px] leading-[1.55] text-muted-foreground">{children}</p>
          {actions ? <div className="mt-3.5 flex flex-wrap gap-2">{actions}</div> : null}
          {hint ? (
            <p className="mt-3 flex items-start gap-2 border-t border-border pt-3 text-[12.5px] leading-normal text-subtle">
              <HintIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>{hint}</span>
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
