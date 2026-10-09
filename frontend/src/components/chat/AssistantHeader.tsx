import { FlaskConical, MessagesSquare, RotateCcw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface AssistantHeaderProps {
  /** Development-only: the simulated assistant is active (VITE_USE_MOCK_API). */
  mock: boolean;
  canReset: boolean;
  onReset: () => void;
}

export function AssistantHeader({ mock, canReset, onReset }: AssistantHeaderProps) {
  return (
    <div className="flex shrink-0 items-start gap-3.5 border-b border-border bg-card px-4 py-4 sm:px-6 sm:py-5">
      <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-[10px] border border-primary/20 bg-primary-soft text-primary">
        <MessagesSquare className="size-[22px]" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="text-[17px] font-semibold">Enterprise Assistant</h2>
        <p className="mt-[3px] max-w-[74ch] text-[13.5px] text-muted-foreground">
          Ask about company documents. Answers are generated only from sources your account is authorized to read.
        </p>
      </div>
      {mock ? (
        <Badge variant="warning" title="VITE_USE_MOCK_API=true: simulated responses, not the real backend">
          <FlaskConical aria-hidden="true" />
          Mock responses
        </Badge>
      ) : null}
      {canReset ? (
        <Button variant="secondary" size="sm" onClick={onReset} title="New chat">
          <RotateCcw aria-hidden="true" />
          <span className="sr-only sm:not-sr-only">New chat</span>
        </Button>
      ) : null}
    </div>
  );
}
