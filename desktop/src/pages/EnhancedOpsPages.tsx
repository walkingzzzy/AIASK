import { OpsPages } from "./OpsPages";
import type { PageProps } from "./pageUtils";

export function EnhancedOpsPages(props: PageProps) {
  return <OpsPages {...props} />;
}

export function EnhancedGatewayPage(props: PageProps) {
  return <OpsPages {...props} view="workflows" />;
}

export function EnhancedAutomationPage(props: PageProps) {
  return <OpsPages {...props} view="automation" />;
}

export function EnhancedUserPage(props: PageProps) {
  return <OpsPages {...props} view="local-user-memory" />;
}

export function EnhancedLearningRlPage(props: PageProps) {
  return <OpsPages {...props} view="learning-rl" />;
}

