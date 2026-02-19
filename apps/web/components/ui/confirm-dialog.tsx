'use client';

export function ConfirmDialog({
  open,
  title = '确认操作',
  message,
  onConfirm,
  onCancel,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
}: {
  open: boolean;
  title?: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onCancel}>
      <div className="bg-white rounded-xl p-6 w-[380px] shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="mt-0 mb-2 text-base font-semibold">{title}</h3>
        <p className="text-text-secondary text-sm mb-4">{message}</p>
        <div className="flex justify-end gap-2">
          <button onClick={onCancel} className="px-4 py-1.5 border border-border rounded text-sm cursor-pointer">
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-1.5 rounded text-sm text-white cursor-pointer ${danger ? 'bg-danger' : 'bg-primary'}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
