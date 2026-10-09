import { FileText, X, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatFileSize } from "@/lib/format";

interface SelectedFileProps {
  file: File;
  onRemove: () => void;
  disabled?: boolean;
  icon?: LucideIcon;
}

export function SelectedFile({ file, onRemove, disabled = false, icon: Icon = FileText }: SelectedFileProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-3.5 py-3" data-testid="selected-file">
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-[7px] border border-border bg-muted text-muted-foreground">
        <Icon className="size-[18px]" aria-hidden="true" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[13.5px] font-semibold">{file.name}</span>
        <span className="text-xs tabular-nums text-muted-foreground">{formatFileSize(file.size)}</span>
      </span>
      <Button variant="ghost" size="icon" onClick={onRemove} disabled={disabled} aria-label="Remove selected file">
        <X aria-hidden="true" />
      </Button>
    </div>
  );
}
