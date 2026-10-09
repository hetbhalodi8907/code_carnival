import { useId } from "react";

import { cn } from "@/lib/utils";

/** Abstract "N" monogram: two pillars joined by a single diagonal, inside a soft tile. */
export function NexoraMark({ className }: { className?: string }) {
  const gradientId = useId();
  return (
    <svg viewBox="0 0 40 40" aria-hidden="true" className={cn("size-9 shrink-0", className)}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--primary)" />
          <stop offset="100%" stopColor="var(--success)" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="11" className="fill-card stroke-border" strokeWidth="1" />
      <path
        d="M12.5 28V12l15 16V12"
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function NexoraWordmark({
  subtitle = "Secure AI Workspace",
  className,
  textClassName,
}: {
  subtitle?: string;
  className?: string;
  /** e.g. "hidden sm:block" to show only the mark on narrow screens. */
  textClassName?: string;
}) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <NexoraMark />
      <div className={cn("leading-tight", textClassName)}>
        <div className="text-[15px] font-semibold tracking-[0.22em]">NEXORA</div>
        {subtitle ? <div className="text-xs text-muted-foreground">{subtitle}</div> : null}
      </div>
    </div>
  );
}
