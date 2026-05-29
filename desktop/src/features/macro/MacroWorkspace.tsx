import { FinancialCapabilityWorkspace } from "../financial-manager/FinancialCapabilityWorkspace";

export function MacroWorkspace({
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
      description="宏观指标和市场概览以只读方式展示，用于把 GDP/CPI/PMI/M2 等环境变量带回投资分析。"
      endpoint={endpoint}
      eyebrow="宏观经济"
      title="宏观指标与市场环境"
      userId={userId}
      actions={[
        { capability_id: "macro", action_id: "indicators", label: "宏观指标", description: "读取宏观指标时间序列。" },
        { capability_id: "macro", action_id: "overview", label: "市场概览", description: "汇总当前宏观与市场环境。" }
      ]}
    />
  );
}
