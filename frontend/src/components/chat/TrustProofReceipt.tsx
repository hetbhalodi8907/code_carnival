import { ChevronDown, ShieldCheck } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CitationCheck } from "@/types/api";
import type { AssistantResult } from "@/types/assistant";

type Receipt = Extract<AssistantResult, { kind: "answered" | "insufficient_context" }>;

const PROVIDER_LABELS: Record<string, string> = { groq: "Groq (cloud)", lm_studio: "LM Studio (local)" };

type Tone = "success" | "warning" | "muted";

function Row({ label, tone, value, detail }: { label: string; tone: Tone; value: ReactNode; detail?: string }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-4">
      <dt className="w-44 shrink-0 text-[12.5px] font-medium text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-[13px]">
        <Badge variant={tone} className="h-auto min-h-[22px] whitespace-normal py-0.5 text-left">
          {value}
        </Badge>
        {detail ? <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p> : null}
      </dd>
    </div>
  );
}

function citationRow(check: CitationCheck | undefined): { tone: Tone; value: string; detail?: string } {
  switch (check) {
    case "passed":
      return { tone: "success", value: "Passed", detail: "Every [S#] reference in the answer matched a source retrieved for you." };
    case "partial":
      return { tone: "warning", value: "Partial", detail: "Some references were removed because they matched no source retrieved for you." };
    case "none":
      return { tone: "muted", value: "No citations", detail: "The answer does not cite any retrieved source." };
    default:
      return { tone: "muted", value: "Not available" };
  }
}

function modelText(provider: string | null, model: string | null): string {
  const label = provider ? (PROVIDER_LABELS[provider] ?? provider) : null;
  if (label && model) return `${label} · ${model}`;
  return label ?? model ?? "Not available";
}

/**
 * A collapsed-by-default receipt under an assistant reply. Every value comes from the server's response
 * (status, citation check and the optional trust_proof object); anything the server did not substantiate
 * reads "Not available". It is never shown for a denial or an error, and it makes no claim that a
 * statement is factually correct: a passed citation check only shows a cited source was retrieved for the user.
 */
export function TrustProofReceipt({ result }: { result: Receipt }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const answered = result.kind === "answered";

  return (
    <section className="mt-2 rounded-xl border border-border bg-surface-2" aria-label="TrustProof: answer integrity" data-testid="trustproof">
      <h3 className="m-0">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={panelId}
          className="flex w-full items-center gap-2 rounded-xl px-3.5 py-2.5 text-left text-[13px] font-semibold hover:bg-muted"
        >
          <ShieldCheck className="size-4 text-primary" aria-hidden="true" />
          TrustProof
          <span className="font-normal text-subtle">Answer integrity</span>
          <ChevronDown className={cn("ml-auto size-4 text-subtle transition-transform", open && "rotate-180")} aria-hidden="true" />
        </button>
      </h3>
      {open ? (
        <div id={panelId} className="border-t border-border px-3.5 pb-3.5 pt-3">
          <dl className="flex flex-col gap-3">
            <Row
              label="Response"
              tone={answered ? "success" : "muted"}
              value={answered ? "Answer generated" : "No answer generated"}
            />
            {answered ? (
              <>
                <Row
                  label="Authorization"
                  tone={result.trust ? "success" : "muted"}
                  value={result.trust ? "Access-controlled retrieval applied" : "Not available"}
                  detail={result.trust ? "Only sources your account is permitted to read were retrieved for this answer." : undefined}
                />
                <Row label="Citation validation" {...citationRow(result.citationCheck)} />
                <Row
                  label="Authorized sources used"
                  tone="muted"
                  value={result.trust ? String(result.trust.authorizedSourceCount) : "Not available"}
                />
                <Row
                  label="Model used"
                  tone="muted"
                  value={result.trust ? modelText(result.trust.provider, result.trust.model) : "Not available"}
                />
              </>
            ) : (
              <>
                <Row
                  label="Evidence"
                  tone="warning"
                  value="Insufficient"
                  detail="The sources you are permitted to read did not contain enough information to answer."
                />
                <Row label="Citation validation" tone="muted" value="Not applicable" />
              </>
            )}
          </dl>
          <p className="mt-3 border-t border-border pt-2.5 text-xs leading-relaxed text-subtle">
            A passed citation check shows that cited sources were retrieved for you. It does not verify that every statement in the answer is correct.
          </p>
        </div>
      ) : null}
    </section>
  );
}
