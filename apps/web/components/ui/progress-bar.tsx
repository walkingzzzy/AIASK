export function ProgressBar({
  value,
  max = 1,
  className = '',
  color,
}: {
  value: number;
  max?: number;
  className?: string;
  color?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={`w-full bg-gray-200 rounded-full h-2 ${className}`}>
      <div
        className="h-2 rounded-full transition-all"
        style={{ width: `${pct}%`, backgroundColor: color ?? '#1a73e8' }}
      />
    </div>
  );
}
