export default function Loading() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="flex items-center gap-3">
        <div className="relative w-5 h-5">
          <div className="absolute inset-0 rounded-full border-2 border-primary/30" />
          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-primary animate-[spin_0.8s_linear_infinite]" />
        </div>
        <span className="text-text-secondary text-sm">加载中...</span>
      </div>
    </div>
  );
}
