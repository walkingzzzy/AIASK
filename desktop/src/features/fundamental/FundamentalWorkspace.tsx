import { FinancialCapabilityWorkspace } from "../financial-manager/FinancialCapabilityWorkspace";

export function FundamentalWorkspace({
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
      description="基本面分析、杜邦分解和同行对比统一收拢为业务入口，便于从后端 manager 能力直接进入。"
      endpoint={endpoint}
      eyebrow="基本面"
      title="财务质量与同行对比"
      userId={userId}
      actions={[
        { capability_id: "fundamental", action_id: "analyze", label: "基本面分析", description: "生成综合基本面分析。" },
        { capability_id: "fundamental", action_id: "dupont", label: "杜邦分析", description: "拆解盈利能力、周转和杠杆因子。" },
        { capability_id: "fundamental", action_id: "compare", label: "同行对比", description: "按 peers 参数进行同行比较。" }
      ]}
    />
  );
}
