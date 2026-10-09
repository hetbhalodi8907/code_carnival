import { Lock, Send } from "lucide-react";
import { useLayoutEffect, type KeyboardEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";

const MAX_QUESTION_LENGTH = 2000;

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  pending: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

export function Composer({ value, onChange, onSubmit, pending, textareaRef }: ComposerProps) {
  // Grow with the content; max-h on the textarea caps it.
  useLayoutEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [value, textareaRef]);

  const canSend = value.trim().length > 0 && !pending;

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onSubmit();
    }
  }

  return (
    <div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canSend) onSubmit();
        }}
        className="flex items-end gap-2.5 rounded-xl border border-border-strong bg-card py-2 pl-3.5 pr-2 shadow-xs transition-[border-color,box-shadow] focus-within:border-primary focus-within:ring-[3px] focus-within:ring-ring"
      >
        <label htmlFor="question" className="sr-only">
          Ask a question
        </label>
        <Textarea
          id="question"
          ref={textareaRef}
          rows={1}
          value={value}
          maxLength={MAX_QUESTION_LENGTH}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about company knowledge…"
          className="max-h-[140px] min-h-[36px] flex-1 py-1.5"
        />
        <Button type="submit" size="icon" disabled={!canSend} aria-label="Send question" className="size-10">
          {pending ? <Spinner className="size-[18px]" /> : <Send className="size-[18px]" aria-hidden="true" />}
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <span className="inline-flex items-center gap-[7px] text-xs text-subtle">
          <Lock className="size-3.5" aria-hidden="true" />
          Results are limited to sources your account may read.
        </span>
        <span className="hidden text-[11.5px] text-subtle sm:inline">
          <kbd className="rounded-[5px] border border-b-2 border-border bg-muted px-[5px] py-px font-mono text-[11px] text-muted-foreground">Enter</kbd>{" "}
          to send · <kbd className="rounded-[5px] border border-b-2 border-border bg-muted px-[5px] py-px font-mono text-[11px] text-muted-foreground">Shift</kbd>
          +<kbd className="rounded-[5px] border border-b-2 border-border bg-muted px-[5px] py-px font-mono text-[11px] text-muted-foreground">Enter</kbd>{" "}
          for a new line
        </span>
      </div>
    </div>
  );
}
