import { PageContainer, SkeletonCard, SkeletonTable } from '@/components/ui';

export default function StockLoading() {
  return (
    <PageContainer>
      <div className="h-7 w-32 rounded bg-glass-border/40 animate-pulse mb-4" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
        <SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard />
      </div>
      <div className="h-[420px] glass rounded-xl animate-pulse mb-4" />
      <SkeletonTable rows={6} cols={4} />
    </PageContainer>
  );
}
