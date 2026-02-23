type Variant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';

const VARIANT_CLASSES: Record<Variant, string> = {
  success: 'bg-success/15 text-success',
  danger: 'bg-danger/15 text-danger',
  warning: 'bg-warning/15 text-warning',
  info: 'bg-primary/15 text-primary',
  neutral: 'bg-glass text-text-secondary',
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
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium backdrop-blur-sm ${VARIANT_CLASSES[variant]} ${className}`}>
      {children}
    </span>
  );
}
