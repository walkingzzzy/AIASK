import { readFileSync } from 'node:fs';
import type { FixtureBundle } from '../contracts';

let cachedBundle: FixtureBundle | null = null;

export function getBundle(): FixtureBundle {
  if (cachedBundle) {
    return cachedBundle;
  }

  const rawBundle = process.env.E2E_FIXTURE_BUNDLE
    ?? (process.env.E2E_FIXTURE_BUNDLE_PATH
      ? readFileSync(process.env.E2E_FIXTURE_BUNDLE_PATH, 'utf8')
      : null);

  if (!rawBundle) {
    throw new Error('missing E2E_FIXTURE_BUNDLE or E2E_FIXTURE_BUNDLE_PATH');
  }

  cachedBundle = JSON.parse(rawBundle) as FixtureBundle;
  return cachedBundle;
}
