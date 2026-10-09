import { ArrowUp } from "lucide-react";
import { useLayoutEffect, type KeyboardEvent, type RefObject } from "react";

import { Button } from "@/components/ui/button";
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
  // Grow with the content up to max-h-40.
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
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSubmit();
      }}
      className="rounded-2xl border border-border bg-card shadow-[0_12px_40px_-20px_rgb(0_0_0/0.6)] transition-[border-color,box-shadow] focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-ring/25"
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
        placeholder="Ask about authorized company information…"
        className="max-h-40 min-h-[52px] px-4 pt-3.5"
      />
      <div className="flex items-center justify-between gap-3 px-3 pb-3">
        <span className="hidden pl-1 text-xs text-muted-foreground sm:inline">
          <kbd className="font-sans">Enter</kbd> to send · <kbd className="font-sans">Shift + Enter</kbd> for a new line
        </span>
        <Button type="submit" size="icon" disabled={!canSend} aria-label="Send question" className="ml-auto rounded-xl">
          <ArrowUp aria-hidden="true" />
        </Button>
      </div>
    </form>
  );
}
