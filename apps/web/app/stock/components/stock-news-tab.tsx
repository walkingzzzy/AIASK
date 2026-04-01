import { SectionCard } from '@/components/ui';
import { fmt } from '@/lib/api';
import type { StockNewsItem } from '@aiask/shared-types';

type StockNewsTabProps = {
  newsItems: StockNewsItem[];
  isFetching: boolean;
};

export default function StockNewsTab({ newsItems, isFetching }: StockNewsTabProps) {
  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">最新资讯</h3>
      {newsItems.length > 0 ? (
        <div className="max-h-[500px] space-y-3 overflow-auto">
          {newsItems.slice(0, 20).map((item: Record<string, unknown>, index: number) => (
            <div key={`${String(item.title ?? 'news')}-${index}`} className="panel-soft rounded-[22px] p-4">
              {item.url ? (
                <a
                  href={String(item.url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-primary hover:underline"
                >
                  {fmt(item.title as string)}
                </a>
              ) : (
                <div className="text-sm font-medium">{fmt(item.title as string)}</div>
              )}
              <div className="mt-0.5 text-xs text-text-muted">
                {fmt(item.date as string)} {item.source ? `｜ ${fmt(item.source as string)}` : ''}
              </div>
              {item.summary ? <div className="mt-1 text-xs text-text-secondary">{String(item.summary).slice(0, 120)}</div> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-text-secondary">{isFetching ? '加载中...' : '查询股票后显示相关资讯'}</p>
      )}
    </SectionCard>
  );
}
