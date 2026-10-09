import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "flex h-10 w-full min-w-0 rounded-lg border border-input bg-card px-3 text-[14.5px] text-foreground transition-[border-color,box-shadow] outline-none placeholder:text-subtle",
        "hover:border-[#c2c9d2] focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-ring",
        "aria-invalid:border-destructive aria-invalid:focus-visible:ring-destructive/20 disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
