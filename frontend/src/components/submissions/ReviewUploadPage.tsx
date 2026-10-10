import { FileUp, ScanText } from "lucide-react";
import { useState } from "react";

import { MySubmissions } from "@/components/submissions/MySubmissions";
import { SubmitForReview, type SubmissionKind } from "@/components/submissions/SubmitForReview";

/**
 * The upload page for accounts that submit files for CEO approval (they hold documents:submit but not
 * documents:write). The same page serves PDFs and images; the server decides every permission.
 */
export function ReviewUploadPage({ kind }: { kind: SubmissionKind }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const Icon = kind === "pdf" ? FileUp : ScanText;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="review-upload-page">
      <div className="flex shrink-0 items-start gap-3.5 border-b border-border bg-card px-4 py-4 sm:px-6 sm:py-5">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-primary/20 bg-primary-soft text-primary">
          <Icon className="size-[22px]" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-[17px] font-semibold">{kind === "pdf" ? "Upload Documents" : "Upload Images"}</h2>
          <p className="mt-[3px] max-w-[74ch] text-[13.5px] text-muted-foreground">
            {kind === "pdf"
              ? "Submit a PDF for review. The CEO approves it before it is indexed, and only then can it be searched."
              : "Submit a scanned page, photo or screenshot for review. The CEO approves it before its text is read and indexed."}
          </p>
        </div>
      </div>
      <div className="mx-auto flex max-w-[820px] flex-col gap-4 p-4 sm:p-6">
        <SubmitForReview kind={kind} onSubmitted={() => setRefreshKey((value) => value + 1)} />
        <MySubmissions refreshKey={refreshKey} />
      </div>
    </div>
  );
}
