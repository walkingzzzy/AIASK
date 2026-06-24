import { AlertTriangle } from "lucide-react";

import { LinkCard, PageShell, Panel, StatusBadge } from "../components/ui";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { FinancePages } from "./FinancePages";
import { dataObject, metric, type PageProps } from "./pageUtils";

function EnhancedFinanceLabPage({ api }: PageProps) {
  const dataStatus = useAsyncResource(() => api.dataStatus(), [api]);
  const radarStatus = useAsyncResource(() => api.stockRadarStatus(), [api]);
  const managerStatus = useAsyncResource(() => api.financialManagerStatus(), [api]);
  const data = dataObject(dataStatus.data, {});
  const freshness = dataObject(data.freshness, {});
  const radar = dataObject(radarStatus.data, {});
  const manager = dataObject(managerStatus.data, {});
  const staleCount = Number(freshness.stale_count || 0);

  return (
    <PageShell
      title="Finance Lab"
      description="V1 金融研究主入口，统一承接数据、雷达、市场、量化和经理台，不再直接暴露四工厂产品入口。"
      metrics={[
        metric("数据门禁", freshness.status || "unknown", staleCount > 0 ? "warning" : "success"),
        metric("过期条目", staleCount, staleCount > 0 ? "warning" : "success"),
        metric("雷达状态", radar.status || "unknown", radar.status === "ready" ? "success" : "warning"),
        metric("经理台", manager.ready ? "ready" : "degraded", manager.ready ? "success" : "warning")
      ]}
    >
      <div className="grid-3 finance-lab-overview">
        <LinkCard to="/stock-data-sources" title="数据源" detail="查看和配置股票数据源。" tone="info" />
        <LinkCard to="/data-sync" title="数据与同步" detail="检查 freshness、missing、stale 和 dry-run 计划。" tone={staleCount > 0 ? "warning" : "success"} />
        <LinkCard to="/stock-radar" title="股票雷达" detail="候选、摘要、风险提示和受控动作。" tone="success" />
        <LinkCard to="/market-temperature" title="市场温度" detail="市场广度、行业冷热和缓存验证。" tone="info" />
        <LinkCard to="/quant-research" title="量化研究" detail="Preset、运行、报告和证据链。" tone="neutral" />
        <LinkCard to="/financial-manager" title="金融经理台" detail="目录、状态、查询和券商只读信息。" tone="gated" />
      </div>

      <Panel title="V1 边界说明" className="v1-boundary-notice">
        <div className="boundary-copy">
          <AlertTriangle size={16} />
          <div>
            <strong>四工厂能力继续隐藏为内部高级能力。</strong>
            <p>Strategy、Factor、Incubation、Factory Events 仅保留重定向，不再作为直接产品入口。</p>
          </div>
        </div>
      </Panel>
    </PageShell>
  );
}

export function EnhancedFinancePages(props: PageProps) {
  if (props.view === "finance-lab") {
    return <EnhancedFinanceLabPage {...props} />;
  }
  return <FinancePages {...props} />;
}

export function EnhancedFinanceLabPageHost(props: PageProps) {
  return <EnhancedFinanceLabPage {...props} />;
}

export function EnhancedDataSyncPage(props: PageProps) {
  return <FinancePages {...props} view="data-sync" />;
}

export function EnhancedStockRadarPage(props: PageProps) {
  return <FinancePages {...props} view="stock-radar" />;
}

export function EnhancedQuantResearchPage(props: PageProps) {
  return <FinancePages {...props} view="quant-research" />;
}

