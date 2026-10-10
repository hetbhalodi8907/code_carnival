import { Lock } from "lucide-react";
import { Link } from "react-router";

import { StateBlock } from "@/components/feedback/StateBlock";
import { Button } from "@/components/ui/button";

/**
 * Shown on an upload page instead of the form when the signed-in account can neither upload directly
 * (documents:write) nor submit for approval (documents:submit). It is a courtesy, not a security boundary:
 * the server checks the permission on every request. No upload control is rendered here.
 */
export function UploadLocked({ kind }: { kind: "PDFs" | "images" }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6" data-testid="upload-locked">
      <div className="mx-auto max-w-[720px]">
        <StateBlock
          icon={Lock}
          tone="warning"
          title="Uploading isn't available for your account"
          actions={
            <Button asChild size="sm">
              <Link to="/app/chat">Back to the assistant</Link>
            </Button>
          }
          hint="This page only explains the restriction. The server checks the documents:submit permission on every submission."
        >
          Submitting {kind} requires the documents:submit permission, which this account does not have. This account can
          still ask the assistant about documents it has been granted access to.
        </StateBlock>
      </div>
    </div>
  );
}
