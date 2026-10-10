import { Badge } from "@/components/ui/badge";
import type { Submission, SubmissionStatus } from "@/types/submissions";

const STATUS: Record<SubmissionStatus, { label: string; variant: "warning" | "default" | "success" | "destructive"; detail: string }> = {
  pending_approval: {
    label: "Pending approval",
    variant: "warning",
    detail: "Waiting for the CEO to review it. It is not searchable.",
  },
  indexing: {
    label: "Approved · Indexing",
    variant: "default",
    detail: "Approved. The server is reading and indexing it. It is not searchable yet.",
  },
  ready: { label: "Ready to search", variant: "success", detail: "Approved and indexed." },
  rejected: { label: "Rejected", variant: "destructive", detail: "The CEO did not approve it. The file was deleted." },
  failed: {
    label: "Failed",
    variant: "destructive",
    detail: "Approved, but processing failed. It is not searchable. The CEO can retry.",
  },
};

/** The status in words as well as colour. "Ready to search" appears only for status "ready" from the server. */
export function SubmissionStatusBadge({ status }: { status: SubmissionStatus }) {
  const { label, variant } = STATUS[status];
  return <Badge variant={variant}>{label}</Badge>;
}

/** What the status means for the person looking at it, plus any safe reason the server recorded. */
export function SubmissionNote({ submission }: { submission: Submission }) {
  return (
    <div className="text-xs leading-relaxed text-muted-foreground">
      <p>{STATUS[submission.status].detail}</p>
      {submission.status === "rejected" && submission.rejectionReason ? (
        <p className="mt-0.5">
          <span className="font-semibold text-foreground">Reason:</span> {submission.rejectionReason}
        </p>
      ) : null}
      {submission.status === "failed" && submission.failureMessage ? (
        <p className="mt-0.5 text-destructive-strong">{submission.failureMessage}</p>
      ) : null}
    </div>
  );
}
