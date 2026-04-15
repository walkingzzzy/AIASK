import { writeFile } from 'node:fs/promises';
import { type Page, type Response, type TestInfo } from '@playwright/test';
import { assertNoCriticalPageIssues, createPageIssueCollector } from '../../helpers/app';
import type { SurfaceSpec } from '../contracts';

type IssueCollector = ReturnType<typeof createPageIssueCollector>;

export type ScenarioAudit = {
  collector: IssueCollector;
  apiSummary: string[];
  detach: () => void;
};

export type ScenarioHealthOptions = Parameters<typeof assertNoCriticalPageIssues>[1];

function formatUrl(input: string) {
  try {
    const url = new URL(input);
    return `${url.pathname}${url.search}`;
  } catch {
    return input;
  }
}

export function startScenarioAudit(page: Page): ScenarioAudit {
  const collector = createPageIssueCollector(page);
  const apiSummary: string[] = [];

  const onResponse = (response: Response) => {
    const url = response.url();
    if (!url.includes('/api/')) {
      return;
    }
    apiSummary.push(`${response.status()} ${response.request().method()} ${formatUrl(url)}`);
    if (apiSummary.length > 25) {
      apiSummary.shift();
    }
  };

  page.on('response', onResponse);

  return {
    collector,
    apiSummary,
    detach: () => {
      collector.dispose();
      page.off('response', onResponse);
    },
  };
}

export function assertScenarioHealthy(audit: ScenarioAudit, options?: ScenarioHealthOptions) {
  assertNoCriticalPageIssues(audit.collector, options);
}

export async function attachScenarioAudit(
  testInfo: TestInfo,
  surface: SurfaceSpec,
  scenarioId: string,
  audit: ScenarioAudit,
  extra?: Record<string, unknown>,
) {
  const payload = {
    surfaceId: surface.surfaceId,
    scenarioId,
    route: surface.route,
    auth: surface.auth,
    api5xx: audit.collector.api5xx,
    httpErrors: audit.collector.httpErrors,
    consoleErrors: audit.collector.consoleErrors,
    pageErrors: audit.collector.pageErrors,
    requestFailures: audit.collector.requestFailures,
    apiSummary: audit.apiSummary,
    ...extra,
  };

  const auditPath = testInfo.outputPath(`audit-${surface.surfaceId}-${scenarioId}.json`);
  await writeFile(auditPath, JSON.stringify(payload, null, 2), 'utf8');
  await testInfo.attach('runtime-audit', {
    path: auditPath,
    contentType: 'application/json',
  });
}
