type Variant = 'success' | 'danger' | 'warning' | 'info' | 'neutral';

const VARIANT_CLASSES: Record<Variant, string> = {
  success: 'bg-emerald-100 text-emerald-800',
  danger: 'bg-red-100 text-red-800',
  warning: 'bg-amber-100 text-amber-800',
  info: 'bg-blue-100 text-blue-800',
  neutral: 'bg-gray-100 text-gray-700',
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
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${VARIANT_CLASSES[variant]} ${className}`}>
      {children}
    </span>
  );
}
