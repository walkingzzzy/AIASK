import { FinancialCapabilityWorkspace } from "../financial-manager/FinancialCapabilityWorkspace";

export function DecisionWorkspace({
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
      description="买入、卖出、决策共识和统一决策集中展示，仍通过 Financial Manager 安全 facade 查询。"
      endpoint={endpoint}
      eyebrow="买卖决策"
      title="决策建议与共识"
      userId={userId}
      actions={[
        { capability_id: "decision", action_id: "should_buy", label: "买入建议", description: "按当前后端决策链生成买入评估。" },
        { capability_id: "decision", action_id: "should_sell", label: "卖出建议", description: "结合买入价和持有期生成卖出评估。" },
        { capability_id: "decision", action_id: "consensus", label: "决策共识", description: "汇总多路径决策信号。" },
        { capability_id: "decision", action_id: "unified", label: "统一决策", description: "读取统一决策摘要或明细。" }
      ]}
    />
  );
}
