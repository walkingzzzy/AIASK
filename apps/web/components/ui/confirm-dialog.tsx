'use client';

import { ReactNode, useEffect, useRef, useId } from 'react';

export function ConfirmDialog({
  open,
  title = '确认操作',
  message,
  children,
  onConfirm,
  onCancel,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  confirmDisabled = false,
}: {
  open: boolean;
  title?: string;
  message?: string;
  children?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  confirmDisabled?: boolean;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    if (!open) return;
    if (confirmDisabled) cancelRef.current?.focus();
    else confirmRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') { onCancel(); return; }
      if (e.key === 'Tab') {
        const els = [cancelRef.current, confirmRef.current].filter(Boolean) as HTMLElement[];
        if (els.length < 2) return;
        const idx = els.indexOf(document.activeElement as HTMLElement);
        if (e.shiftKey) {
          e.preventDefault();
          els[(idx - 1 + els.length) % els.length].focus();
        } else {
          e.preventDefault();
          els[(idx + 1) % els.length].focus();
        }
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [confirmDisabled, open, onCancel]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onCancel}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="glass-strong rounded-2xl p-6 w-[420px] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id={titleId} className="mt-0 mb-2 text-base font-semibold">{title}</h3>
        <div id={descId} className="text-text-secondary text-sm mb-4">
          {children ?? message}
        </div>
        <div className="flex justify-end gap-2">
          <button ref={cancelRef} onClick={onCancel} className="px-4 py-1.5 glass rounded-lg text-sm cursor-pointer">
            {cancelText}
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            disabled={confirmDisabled}
            className={`px-4 py-1.5 rounded-lg text-sm text-white ${confirmDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} ${danger ? 'bg-danger' : 'bg-primary'}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
