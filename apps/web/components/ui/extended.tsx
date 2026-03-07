'use client';

import { useEffect, useId, useRef } from 'react';

/** T-023: Modal component */
export function Modal({
    open,
    onClose,
    title,
    children,
    className = '',
}: {
    open: boolean;
    onClose: () => void;
    title?: string;
    children: React.ReactNode;
    className?: string;
}) {
    const dialogRef = useRef<HTMLDialogElement>(null);
    const titleId = useId();

    useEffect(() => {
        if (open) dialogRef.current?.showModal();
        else dialogRef.current?.close();
    }, [open]);

    return (
        <dialog
            ref={dialogRef}
            onClose={onClose}
            aria-modal="true"
            aria-labelledby={title ? titleId : undefined}
            className={`fixed inset-0 z-50 m-auto max-w-lg w-[90%] rounded-xl glass-strong border border-glass-border shadow-2xl p-0 backdrop:bg-black/50 backdrop:backdrop-blur-sm ${className}`}
        >
            {title && (
                <div className="flex items-center justify-between px-5 py-3 border-b border-glass-border">
                    <h3 id={titleId} className="font-semibold text-sm">{title}</h3>
                    <button onClick={onClose} aria-label="关闭对话框" className="text-text-secondary hover:text-text cursor-pointer text-lg">✕</button>
                </div>
            )}
            <div className="px-5 py-4">{children}</div>
        </dialog>
    );
}

/** T-023: Tooltip component */
export function Tooltip({
    content,
    children,
    position = 'top',
}: {
    content: string;
    children: React.ReactNode;
    position?: 'top' | 'bottom' | 'left' | 'right';
}) {
    const positionClasses = {
        top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
        bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
        left: 'right-full top-1/2 -translate-y-1/2 mr-2',
        right: 'left-full top-1/2 -translate-y-1/2 ml-2',
    };

    return (
        <span className="relative group inline-flex">
            {children}
            <span
                role="tooltip"
                className={`absolute ${positionClasses[position]} px-2 py-1 text-[11px] rounded bg-gray-900 text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50`}
            >
                {content}
            </span>
        </span>
    );
}

/** T-023: Switch toggle component */
export function Switch({
    checked,
    onChange,
    label,
    disabled = false,
}: {
    checked: boolean;
    onChange: (checked: boolean) => void;
    label?: string;
    disabled?: boolean;
}) {
    return (
        <label className={`inline-flex items-center gap-2 ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}>
            <button
                role="switch"
                aria-checked={checked}
                disabled={disabled}
                onClick={() => !disabled && onChange(!checked)}
                className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${checked ? 'bg-primary' : 'bg-gray-500/30'
                    }`}
            >
                <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : ''
                        }`}
                />
            </button>
            {label && <span className="text-sm">{label}</span>}
        </label>
    );
}

/** T-023: Breadcrumb component */
export function Breadcrumb({ items }: { items: { label: string; href?: string }[] }) {
    return (
        <nav className="flex items-center gap-1 text-xs text-text-secondary mb-3" aria-label="面包屑">
            {items.map((item, i) => (
                <span key={i} className="flex items-center gap-1">
                    {i > 0 && <span className="mx-1 opacity-50">/</span>}
                    {item.href ? (
                        <a href={item.href} className="hover:text-primary transition-colors">{item.label}</a>
                    ) : (
                        <span className="text-text">{item.label}</span>
                    )}
                </span>
            ))}
        </nav>
    );
}
