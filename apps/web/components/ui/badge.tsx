type Variant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';

const VARIANT_CLASSES: Record<Variant, string> = {
  success: 'bg-[linear-gradient(180deg,rgba(3,152,85,0.14),rgba(255,255,255,0.48))] text-success border-success/20',
  danger: 'bg-[linear-gradient(180deg,rgba(217,45,32,0.14),rgba(255,255,255,0.48))] text-danger border-danger/20',
  warning: 'bg-[linear-gradient(180deg,rgba(181,71,8,0.14),rgba(255,255,255,0.48))] text-warning border-warning/20',
  info: 'bg-[linear-gradient(180deg,rgba(11,107,203,0.14),rgba(255,255,255,0.48))] text-primary border-primary/20',
  neutral: 'bg-[linear-gradient(180deg,rgba(255,255,255,0.7),rgba(246,250,255,0.42))] text-text-secondary border-border',
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
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.72)] backdrop-blur-xl ${VARIANT_CLASSES[variant]} ${className}`}>
      {children}
    </span>
  );
}
