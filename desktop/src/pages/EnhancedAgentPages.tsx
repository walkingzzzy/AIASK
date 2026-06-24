import { AgentPages } from "./AgentPages";
import type { PageProps } from "./pageUtils";

export function EnhancedAgentPages(props: PageProps) {
  return <AgentPages {...props} />;
}

export function EnhancedSessionsRunsPage(props: PageProps) {
  return <AgentPages {...props} view="sessions-runs" />;
}

export function EnhancedToolsApprovalsPage(props: PageProps) {
  return <AgentPages {...props} view="tools-approvals" />;
}

