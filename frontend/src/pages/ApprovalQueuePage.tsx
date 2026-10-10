import { CircleCheck, ClipboardCheck, Eye, EyeOff, FileText, ImageIcon, Lock, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { EmptyNote } from "@/components/dashboard/primitives";
import { StateBlock } from "@/components/feedback/StateBlock";
import { SubmissionNote, SubmissionStatusBadge } from "@/components/submissions/SubmissionStatus";
import { SubmissionPreview } from "@/components/submissions/SubmissionPreview";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/context/useAuth";
import { formatDateTime } from "@/lib/dashboardFormat";
import { formatFileSize } from "@/lib/format";
import { ApiError, toFriendlyError, type FriendlyError } from "@/services/api";
import { approveSubmission, listApprovalQueue, rejectSubmission } from "@/services/submissions";
import type { Submission } from "@/types/submissions";

const MAX_REASON = 300;

type Pending = "approving" | "rejecting";

function metadata(item: Submission): string {
  const parts = [item.sourceType === "pdf" ? "PDF" : "Image", formatFileSize(item.sizeBytes)];
  if (item.pageCount !== null) parts.push(`${item.pageCount} ${item.pageCount === 1 ? "page" : "pages"}`);
  if (item.imageWidth !== null && item.imageHeight !== null) parts.push(`${item.imageWidth}×${item.imageHeight} px`);
  return parts.join(" · ");
}

/** Why an approve or reject call did not complete, in fixed copy (the server's 409 text is safe and specific). */
function describeActionFailure(error: unknown): string {
  if (error instanceof ApiError && error.status === 409 && error.serverMessage) return error.serverMessage;
  if (error instanceof ApiError && error.status === 404) return "This submission no longer exists. Refresh the queue.";
  return toFriendlyError(error).message;
}

function QueueItem({
  item,
  pending,
  note,
  onApprove,
  onReject,
}: {
  item: Submission;
  pending: Pending | undefined;
  note: string | undefined;
  onApprove: () => void;
  onReject: (reason: string | null) => void;
}) {
  const [previewing, setPreviewing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const Icon = item.sourceType === "image" ? ImageIcon : FileText;
  const decided = item.status === "ready" || item.status === "rejected";
  const busy = pending !== undefined;
  const canPreview = item.previewAvailable && !decided;

  return (
    <li className="py-4 first:pt-0 last:pb-0" data-testid="queue-item">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="flex min-w-0 items-start gap-2.5">
          <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0">
            <p className="break-all text-sm font-semibold leading-snug">{item.filename}</p>
            <p className="text-xs text-muted-foreground">{metadata(item)}</p>
            <p className="text-xs text-muted-foreground">
              Submitted by <span className="font-medium text-foreground">{item.submitter?.name ?? "unknown"}</span>
              {item.submitter ? ` (${item.submitter.email})` : ""} on {formatDateTime(item.createdAt)}
            </p>
          </div>
        </div>
        <SubmissionStatusBadge status={item.status} />
      </div>

      <div className="mt-2 pl-[26px]">
        <SubmissionNote submission={item} />
        {note ? (
          <p className="mt-1.5 text-[12.5px] font-medium text-foreground" role="status">
            {note}
          </p>
        ) : null}

        {!decided ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {canPreview ? (
              <Button variant="secondary" size="sm" onClick={() => setPreviewing((value) => !value)} aria-expanded={previewing}>
                {previewing ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                {previewing ? "Hide preview" : "Preview"}
              </Button>
            ) : null}
            {item.status === "indexing" ? (
              <span className="text-[12.5px] text-muted-foreground" role="status">
                Being indexed…
              </span>
            ) : (
              <>
                <Button size="sm" onClick={onApprove} disabled={busy}>
                  {pending === "approving" ? <Spinner /> : <CircleCheck aria-hidden="true" />}
                  {pending === "approving" ? "Approving and indexing…" : item.status === "failed" ? "Retry approval" : "Approve"}
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setRejecting((value) => !value)} disabled={busy} aria-expanded={rejecting}>
                  <X aria-hidden="true" />
                  Reject
                </Button>
              </>
            )}
          </div>
        ) : null}

        {rejecting && !decided ? (
          <form
            className="mt-3 space-y-2 rounded-lg border border-border bg-surface-2 p-3"
            onSubmit={(event) => {
              event.preventDefault();
              onReject(reason.trim() || null);
              setRejecting(false);
              setReason("");
            }}
          >
            <label htmlFor={`reason-${item.id}`} className="text-[13px] font-medium">
              Reason (optional)
            </label>
            <Textarea
              id={`reason-${item.id}`}
              rows={2}
              maxLength={MAX_REASON}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Shown to the person who submitted it"
            />
            <div className="flex gap-2">
              <Button type="submit" variant="danger" size="sm" disabled={busy}>
                Confirm rejection
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setRejecting(false)}>
                Cancel
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Rejecting deletes the file. It is never indexed.</p>
          </form>
        ) : null}

        {previewing && canPreview ? (
          <div className="mt-3" data-testid="submission-preview">
            <SubmissionPreview submission={item} />
          </div>
        ) : null}
      </div>
    </li>
  );
}

/** The CEO's review queue. The server only serves it to accounts with documents:approve. */
export function ApprovalQueuePage() {
  const { user } = useAuth();
  const canApprove = user?.permissions.includes("documents:approve") ?? false;
  const [items, setItems] = useState<Submission[] | null>(null);
  const [error, setError] = useState<FriendlyError | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<Record<string, Pending>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const inFlight = useRef<AbortController | null>(null);
  const acting = useRef(new Set<string>());

  const load = useCallback(() => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setLoading(true);
    listApprovalQueue(controller.signal)
      .then((list) => {
        setItems(list);
        setNotes({});
        setError(null);
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setError(toFriendlyError(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!canApprove) return;
    load();
    return () => inFlight.current?.abort();
  }, [canApprove, load]);

  if (!canApprove) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6" data-testid="approvals-restricted">
        <div className="mx-auto max-w-[720px]">
          <StateBlock
            icon={Lock}
            tone="warning"
            title="The approval queue isn't available for your account"
            actions={
              <Button asChild size="sm">
                <Link to="/app/dashboard">Back to the dashboard</Link>
              </Button>
            }
            hint="The server checks the documents:approve permission on every request in this queue."
          >
            Reviewing submitted documents is limited to the CEO / Super Admin account.
          </StateBlock>
        </div>
      </div>
    );
  }

  async function act(item: Submission, kind: Pending, run: () => Promise<Submission>) {
    // One action per submission at a time; the ref also blocks a double click before the next render.
    if (acting.current.has(item.id)) return;
    acting.current.add(item.id);
    setPending((current) => ({ ...current, [item.id]: kind }));
    try {
      const updated = await run();
      setItems((current) => current?.map((entry) => (entry.id === item.id ? { ...updated, submitter: updated.submitter ?? entry.submitter } : entry)) ?? current);
      setNotes((current) => ({
        ...current,
        [item.id]:
          updated.status === "ready"
            ? "Approved and indexed. It is searchable only by the person who submitted it, under the existing access rules."
            : updated.status === "rejected"
              ? "Rejected. The file was deleted and nothing was indexed."
              : updated.status === "failed"
                ? "Approval did not complete. Nothing was indexed; you can retry."
                : "Updated.",
      }));
    } catch (failure) {
      setNotes((current) => ({ ...current, [item.id]: describeActionFailure(failure) }));
    } finally {
      acting.current.delete(item.id);
      setPending((current) => {
        const rest = { ...current };
        delete rest[item.id];
        return rest;
      });
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="approval-queue">
      <div className="flex shrink-0 items-start gap-3.5 border-b border-border bg-card px-4 py-4 sm:px-6 sm:py-5">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-primary/20 bg-primary-soft text-primary">
          <ClipboardCheck className="size-[22px]" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[17px] font-semibold">Document Approval Queue</h2>
          <p className="mt-[3px] max-w-[74ch] text-[13.5px] text-muted-foreground">
            Files submitted for review stay in quarantine. Nothing here is searchable, and the assistant cannot see it, until you approve it and
            indexing completes.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={load} disabled={loading} aria-label="Refresh the queue">
          {loading ? <Spinner /> : <RefreshCw aria-hidden="true" />}
          Refresh
        </Button>
      </div>

      <div className="mx-auto flex max-w-[900px] flex-col gap-4 p-4 sm:p-6">
        {error ? (
          <Alert variant="error" role="alert">
            <strong className="font-semibold">{error.title}.</strong> {error.message}
          </Alert>
        ) : null}
        <section className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-5" aria-label="Submissions awaiting a decision">
          {items === null && !error ? (
            <p className="text-sm text-muted-foreground" role="status">
              Loading the queue…
            </p>
          ) : null}
          {items !== null && items.length === 0 ? <EmptyNote>No submissions are waiting for review.</EmptyNote> : null}
          {items !== null && items.length > 0 ? (
            <ul className="m-0 flex list-none flex-col divide-y divide-border p-0">
              {items.map((item) => (
                <QueueItem
                  key={item.id}
                  item={item}
                  pending={pending[item.id]}
                  note={notes[item.id]}
                  onApprove={() => void act(item, "approving", () => approveSubmission(item.id))}
                  onReject={(reason) => void act(item, "rejecting", () => rejectSubmission(item.id, reason))}
                />
              ))}
            </ul>
          ) : null}
          {items !== null && items.some((item) => item.status === "ready" || item.status === "rejected") ? (
            <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
              Decisions you just made stay here until you refresh the queue.
            </p>
          ) : null}
        </section>
      </div>
    </div>
  );
}
