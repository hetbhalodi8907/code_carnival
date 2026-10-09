import { initials } from "@/lib/format";
import { cn } from "@/lib/utils";

const SIZES = {
  sm: "size-[30px] text-[11.5px]",
  md: "size-[34px] text-[12.5px]",
  lg: "size-[62px] text-xl",
};

/** Initials in a soft blue circle. Decorative: the name is always rendered next to it. */
export function Avatar({ name, size = "md", className }: { name: string; size?: keyof typeof SIZES; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-primary-soft font-semibold tracking-wide text-primary",
        SIZES[size],
        className,
      )}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}
