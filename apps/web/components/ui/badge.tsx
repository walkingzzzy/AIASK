type Variant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';

const VARIANT_CLASSES: Record<Variant, string> = {
  success: 'bg-success/12 text-success border-success/20',
  danger: 'bg-danger/12 text-danger border-danger/20',
  warning: 'bg-warning/12 text-warning border-warning/20',
  info: 'bg-primary/12 text-primary border-primary/20',
  neutral: 'bg-surface-alt text-text-secondary border-border',
};

export function Badge({
  children,
  variant = 'neutral',
  className = '',
}: {
  children: React.ReactNode;
  variant?: Variant;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${VARIANT_CLASSES[variant]} ${className}`}>
      {children}
    </span>
  );
}
