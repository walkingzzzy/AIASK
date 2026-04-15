import { type Page, type TestInfo } from '@playwright/test';
import { assertNoHorizontalOverflow, assertProtectedShell } from '../../helpers/app';
import type { FixtureBundle, SurfaceSpec } from '../contracts';
import {
  attachScenarioAudit,
  assertScenarioHealthy,
  startScenarioAudit,
  type ScenarioAudit,
  type ScenarioHealthOptions,
} from './audit';
import { getBundle } from './bundle';

type ScenarioContext = {
  bundle: FixtureBundle;
  audit: ScenarioAudit;
};

type ScenarioOptions = {
  expectProtectedShell?: boolean;
  checkOverflow?: boolean;
  checkCriticalIssues?: boolean;
} & ScenarioHealthOptions;

export async function runScenario(
  page: Page,
  testInfo: TestInfo,
  surface: SurfaceSpec,
  scenarioId: string,
  action: (context: ScenarioContext) => Promise<void>,
  options: ScenarioOptions = {},
) {
  const bundle = getBundle();
  const audit = startScenarioAudit(page);

  try {
    await action({ bundle, audit });

    if (options.expectProtectedShell ?? surface.auth !== 'public') {
      await assertProtectedShell(page);
    }
    if (options.checkOverflow ?? true) {
      await assertNoHorizontalOverflow(page);
    }
    if (options.checkCriticalIssues ?? true) {
      assertScenarioHealthy(audit, options);
    }
  } finally {
    await attachScenarioAudit(testInfo, surface, scenarioId, audit, {
      finalUrl: page.url(),
    });
    audit.detach();
  }
}
