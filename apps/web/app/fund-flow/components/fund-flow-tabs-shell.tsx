import { Badge, QuickAction, QuickActionGrid, TabBar } from '@/components/ui';
import { fundFlowPanelCls } from '@/app/fund-flow/components/fund-flow-panel-styles';
import { FUND_FLOW_TABS, type FundFlowTab } from '@/app/fund-flow/lib/fund-flow-view';

type FundFlowTabsShellProps = {
  activeTabLabel: string;
  activeTab: FundFlowTab;
  onTabChange: (tab: FundFlowTab) => void;
};

export default function FundFlowTabsShell({
  activeTabLabel,
  activeTab,
  onTabChange,
}: FundFlowTabsShellProps) {
  return (
    <>
      <div className={`${fundFlowPanelCls} mb-4`}>
        <QuickActionGrid cols={4}>
          <QuickAction href="/market" icon="📈" title="市场看板" description="先确认指数、板块和题材强弱" />
          <QuickAction href="/research" icon="🧭" title="研究分析" description="把资金流和基本面、估值放一起看" />
          <QuickAction href="/watchlist" icon="⭐" title="自选联动" description="把关注标的拉回到日常跟踪清单" />
          <QuickAction href="/risk" icon="🛡️" title="风险页" description="确认异常资金波动是否伴随仓位风险" />
        </QuickActionGrid>
      </div>

      <div className={`${fundFlowPanelCls} mb-1`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="eyebrow">Flow Tabs</div>
            <div className="mt-2 text-sm leading-7 text-text-secondary">
              先选一个资金维度，再在下方展开具体图表或榜单。个股、板块和北向是最常见的三条起手路径。
            </div>
          </div>
          <Badge variant="neutral">{activeTabLabel}</Badge>
        </div>
        <div className="mt-4">
          <TabBar tabs={FUND_FLOW_TABS} active={activeTab} onChange={onTabChange} />
        </div>
      </div>
    </>
  );
}
