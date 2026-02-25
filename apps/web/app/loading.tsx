import { PageContainer, SkeletonCard, Skeleton } from '@/components/ui';

export default function HomeLoading() {
  return (
    <PageContainer>
      {/* Title */}
      <div className="h-7 w-28 rounded bg-glass-border/40 animate-pulse mb-4" />

      {/* Market Pulse Bar */}
      <Skeleton className="w-full mb-4" height={48} />

      {/* Quick Actions */}
      <div className="grid grid-cols-5 gap-3 mb-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} height={72} />
        ))}
      </div>

      {/* Index Quotes */}
      <div className="glass rounded-xl p-4 mb-4">
        <div className="h-5 w-20 rounded bg-glass-border/40 animate-pulse mb-3" />
        <div className="grid grid-cols-4 gap-3">
          <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
        </div>
      </div>

      {/* Fear-Greed + Sector Fund Flow */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
        <div className="glass rounded-xl p-4">
          <div className="h-5 w-20 rounded bg-glass-border/40 animate-pulse mb-3" />
          <Skeleton height={200} />
        </div>
        <div className="glass rounded-xl p-4">
          <div className="h-5 w-28 rounded bg-glass-border/40 animate-pulse mb-3" />
          <Skeleton height={200} />
        </div>
      </div>

      {/* Limit-Up + North Fund */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="glass rounded-xl p-4">
          <div className="h-5 w-20 rounded bg-glass-border/40 animate-pulse mb-3" />
          <div className="grid grid-cols-3 gap-3">
            <SkeletonCard /><SkeletonCard /><SkeletonCard />
          </div>
        </div>
        <div className="glass rounded-xl p-4">
          <div className="h-5 w-20 rounded bg-glass-border/40 animate-pulse mb-3" />
          <div className="grid grid-cols-2 gap-3">
            <SkeletonCard /><SkeletonCard />
          </div>
        </div>
      </div>
    </PageContainer>
  );
}
