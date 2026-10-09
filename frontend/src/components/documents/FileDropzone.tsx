import { FileUp, type LucideIcon } from "lucide-react";
import { useId, useState, type DragEvent } from "react";

import { MAX_PDF_SIZE_MB } from "@/lib/pdfFile";
import { cn } from "@/lib/utils";

interface FileDropzoneProps {
  /** Every file chosen or dropped; the page decides what to accept. */
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  /** Defaults describe the PDF page; the image page passes its own. */
  accept?: string;
  noun?: string;
  hint?: string;
  icon?: LucideIcon;
}

/** A labelled file input that also accepts drag-and-drop. The native input stays keyboard accessible. */
export function FileDropzone({
  onFiles,
  disabled = false,
  accept = "application/pdf,.pdf",
  noun = "PDF",
  hint = `PDF only, up to ${MAX_PDF_SIZE_MB} MB`,
  icon: Icon = FileUp,
}: FileDropzoneProps) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!disabled) setDragging(true);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) onFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <label
      htmlFor={inputId}
      onDragOver={handleDragOver}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={cn(
        "flex flex-col items-center gap-1.5 rounded-xl border border-dashed px-4 py-9 text-center transition-colors has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-primary",
        dragging ? "border-primary bg-primary-soft" : "border-border-strong bg-surface-2",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-primary hover:bg-primary-soft",
      )}
    >
      <input
        id={inputId}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          onFiles(Array.from(event.target.files ?? []));
          // Clear it so choosing the same file again still fires a change.
          event.target.value = "";
        }}
      />
      <span className="inline-flex size-10 items-center justify-center rounded-[10px] border border-border bg-card text-primary shadow-xs">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <span className="text-sm font-semibold">
        Drag {noun === "image" ? "an" : "a"} {noun} here, or <span className="text-primary">choose a file</span>
      </span>
      <span className="text-[12.5px] text-muted-foreground">{hint}</span>
    </label>
  );
}
