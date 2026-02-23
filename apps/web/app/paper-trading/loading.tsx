import { PageContainer, SkeletonCard, SkeletonTable } from '@/components/ui';

export default function PaperTradingLoading() {
  return (
    <PageContainer>
      <div className="h-7 w-32 rounded bg-glass-border/40 animate-pulse mb-4" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
        <SkeletonCard />
      </div>
      <div className="glass rounded-xl p-4 mb-4">
        <div className="h-4 w-16 rounded bg-glass-border/40 animate-pulse mb-3" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="h-8 rounded bg-glass-border/40 animate-pulse" />
          <div className="h-8 rounded bg-glass-border/40 animate-pulse" />
          <div className="h-8 rounded bg-glass-border/40 animate-pulse" />
          <div className="h-8 rounded bg-glass-border/40 animate-pulse" />
        </div>
      </div>
      <SkeletonTable rows={6} cols={7} />
    </PageContainer>
  );
}
