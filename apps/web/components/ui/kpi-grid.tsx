export function KpiGrid({
  children,
  cols = 4,
  className = '',
}: {
  children: React.ReactNode;
  cols?: 2 | 3 | 4 | 5 | 6;
  className?: string;
}) {
  const colClass = cols === 2 ? 'grid-cols-1 sm:grid-cols-2' : cols === 3 ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3' : cols === 5 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5' : cols === 6 ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4';
  return <div className={`grid gap-3 ${colClass} ${className}`}>{children}</div>;
}
