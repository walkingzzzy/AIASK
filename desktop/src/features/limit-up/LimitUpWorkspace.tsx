import { FinancialCapabilityWorkspace } from "../financial-manager/FinancialCapabilityWorkspace";

export function LimitUpWorkspace({
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
      description="涨停列表、涨停统计和大宗交易入口集中到一个轻量面板，避免这些后端能力只藏在通用列表里。"
      endpoint={endpoint}
      eyebrow="涨停与龙虎"
      title="涨停统计与交易异动"
      userId={userId}
      actions={[
        { capability_id: "limit-up", action_id: "list", label: "涨停板列表", description: "读取当前涨停板列表。" },
        { capability_id: "limit-up", action_id: "statistics", label: "涨停统计", description: "读取涨停统计概览。" },
        { capability_id: "limit-up", action_id: "block_trades", label: "大宗交易", description: "读取大宗交易数据。" }
      ]}
    />
  );
}
