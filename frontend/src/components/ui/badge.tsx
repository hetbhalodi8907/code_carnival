import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex h-[26px] w-fit shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 text-xs font-semibold [&_svg]:size-3.5",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary-soft text-primary",
        muted: "border-border bg-muted text-muted-foreground",
        success: "border-success/25 bg-success-soft text-success-strong",
        warning: "border-warning/30 bg-warning-soft text-warning-strong",
        destructive: "border-destructive/25 bg-destructive-soft text-destructive-strong",
      },
    },
    defaultVariants: { variant: "muted" },
  },
);

function Badge({ className, variant, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
