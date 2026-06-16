import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export function OverlayView({
  title,
  onClose,
  closeLabel = "关闭",
  children,
}: {
  title?: ReactNode;
  onClose: () => void;
  closeLabel?: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="overlay-backdrop" />
        <Dialog.Content
          className="overlay-view"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => event.preventDefault()}
        >
          <div className="overlay-surface">
            <div className="overlay-surface-head">
              {title ? (
                <Dialog.Title className="overlay-surface-title">{title}</Dialog.Title>
              ) : (
                <Dialog.Title className="overlay-surface-title sr-only" />
              )}
              <Dialog.Close className="overlay-close" aria-label={closeLabel}>
                <X size={16} />
              </Dialog.Close>
            </div>
            <div className="overlay-surface-body">{children}</div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
