import { ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";

/** Blue shield tile. Decorative: the NEXORA name is always rendered next to it. */
export function NexoraMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-primary text-white shadow-xs [&>svg]:size-[58%]",
        className,
      )}
      aria-hidden="true"
    >
      <ShieldCheck strokeWidth={1.6} />
    </span>
  );
}

export function NexoraWordmark({
  subtitle = "Secure Enterprise AI Knowledge Platform",
  className,
  textClassName,
  compact = false,
}: {
  subtitle?: string;
  className?: string;
  /** e.g. "hidden sm:block" to show only the mark on narrow screens. */
  textClassName?: string;
  /** Smaller mark and name for the sidebar. */
  compact?: boolean;
}) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <NexoraMark className={compact ? "size-8 rounded-lg" : "size-[38px]"} />
      <div className={cn("flex min-w-0 flex-col gap-px", textClassName)}>
        <span className={cn("font-bold tracking-[0.14em]", compact ? "text-[15px]" : "text-[17px]")}>NEXORA</span>
        {subtitle && !compact ? <span className="text-[11.5px] text-subtle">{subtitle}</span> : null}
      </div>
    </div>
  );
}
