import { FinancialCapabilityWorkspace } from "../financial-manager/FinancialCapabilityWorkspace";

export function AlertsWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
}) {
  return (
    <FinancialCapabilityWorkspace
      apiToken={apiToken}
      controlToken={controlToken}
      description="价格/指标告警和组合条件告警集中展示，当前遵循后端 Financial Manager action 的安全模式。"
      endpoint={endpoint}
      eyebrow="告警管理"
      title="告警检查与规则创建"
      userId={userId}
      actions={[
        { capability_id: "alerts", action_id: "check", label: "检查所有告警", description: "读取当前激活告警的触发状态。" },
        { capability_id: "alerts", action_id: "create_indicator", label: "创建指标告警", description: "按指标、条件和值创建告警规则。" },
        { capability_id: "alerts", action_id: "create_combo", label: "创建组合告警", description: "按多条件组合创建告警规则。" }
      ]}
    />
  );
}
