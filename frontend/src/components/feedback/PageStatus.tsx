import { Spinner } from "@/components/ui/spinner";

/** Full-area loading message, e.g. while a saved session is confirmed with the server. */
export function PageStatus({ children }: { children: string }) {
  return (
    <div className="grid h-full place-items-center bg-background px-4" role="status" aria-live="polite">
      <span className="inline-flex items-center gap-2.5 text-sm text-muted-foreground">
        <Spinner />
        {children}
      </span>
    </div>
  );
}
