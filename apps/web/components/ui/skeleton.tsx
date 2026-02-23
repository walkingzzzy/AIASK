export function Skeleton({
  className = '',
  width,
  height,
}: {
  className?: string;
  width?: string | number;
  height?: string | number;
}) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-glass-border/40 ${className}`}
      style={{ width, height }}
    />
  );
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`glass rounded-xl p-3 ${className}`}>
      <div className="animate-pulse">
        <div className="h-3 w-16 rounded bg-glass-border/40 mb-2" />
        <div className="h-6 w-24 rounded bg-glass-border/40" />
      </div>
    </div>
  );
}

export function SkeletonTable({
  rows = 5,
  cols = 4,
  className = '',
}: {
  rows?: number;
  cols?: number;
  className?: string;
}) {
  return (
    <div className={`glass rounded-xl p-3 ${className}`}>
      <div className="animate-pulse space-y-2">
        <div className="flex gap-3">
          {Array.from({ length: cols }).map((_, i) => (
            <div key={i} className="h-4 rounded bg-glass-border/40 flex-1" />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-3">
            {Array.from({ length: cols }).map((_, j) => (
              <div key={j} className="h-3 rounded bg-glass-border/40 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
