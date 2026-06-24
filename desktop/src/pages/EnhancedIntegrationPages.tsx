import { IntegrationPages } from "./IntegrationPages";
import type { PageProps } from "./pageUtils";

export function EnhancedIntegrationPages(props: PageProps) {
  return <IntegrationPages {...props} />;
}

export function EnhancedMcpPage(props: PageProps) {
  return <IntegrationPages {...props} view="mcp-connectors" />;
}

export function EnhancedConnectorsPage(props: PageProps) {
  return <IntegrationPages {...props} view="mcp-connectors" />;
}

export function EnhancedSkillsPage(props: PageProps) {
  return <IntegrationPages {...props} view="plugins-skills" />;
}

export function EnhancedPluginsPage(props: PageProps) {
  return <IntegrationPages {...props} view="plugins-skills" />;
}

