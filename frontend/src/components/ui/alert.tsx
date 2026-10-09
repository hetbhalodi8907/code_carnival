import { cva, type VariantProps } from "class-variance-authority";
import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const alertVariants = cva("flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-[13.5px] leading-snug", {
  variants: {
    variant: {
      error: "border-destructive/25 bg-destructive-soft text-destructive-strong",
      warning: "border-warning/30 bg-warning-soft text-warning-strong",
      info: "border-primary/20 bg-primary-soft text-primary",
      neutral: "border-border bg-muted text-muted-foreground",
      success: "border-success/25 bg-success-soft text-success-strong",
    },
  },
  defaultVariants: { variant: "neutral" },
});

const ICONS: Record<NonNullable<VariantProps<typeof alertVariants>["variant"]>, LucideIcon> = {
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
  neutral: Info,
  success: CircleCheck,
};

/** Inline message. Pass role="alert" for errors and role="status" for notices. */
export function Alert({ className, variant = "neutral", children, ...props }: ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  const Icon = ICONS[variant ?? "neutral"];
  return (
    <div data-slot="alert" className={cn(alertVariants({ variant }), className)} {...props}>
      <Icon className="mt-px size-[18px] shrink-0" aria-hidden="true" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
