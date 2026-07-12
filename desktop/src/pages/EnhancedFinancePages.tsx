import { AlertTriangle } from "lucide-react";

import { LinkCard, PageShell, Panel } from "../components/ui";
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
      title="金融研究"
      description="金融研究主入口，统一承接数据、雷达、市场、量化、四工厂和经理台；工厂入口走只读 facade 与受控意图。"
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
        <LinkCard to="/strategy-factory" title="策略工厂" detail="状态、运行、领域事件和交易预测只读证据。" tone="info" />
        <LinkCard to="/factor-factory" title="因子工厂" detail="因子挖掘状态、活跃池和 dry-run 意图。" tone="success" />
        <LinkCard to="/incubation" title="孵化工厂" detail="Runner、编排器和观察通道预演。" tone="warning" />
        <LinkCard to="/factory-events" title="工厂事件" detail="事件列表、任务预览、血缘和 outbox。" tone="gated" />
        <LinkCard to="/financial-manager" title="金融经理台" detail="目录、状态、查询和券商只读信息。" tone="gated" />
      </div>

      <Panel title="V1 边界说明" className="v1-boundary-notice">
        <div className="boundary-copy">
          <AlertTriangle size={16} />
          <div>
            <strong>四工厂能力已开放为受控操作台。</strong>
            <p>页面只执行只读调用或创建 dry-run 意图；交易、提交和外部写入继续由后端门禁控制。</p>
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
