import { expect, type Page } from '@playwright/test';
import { assertProtectedShell, dismissOnboarding, waitForSettledUi } from '../../helpers/app';
import type { FixtureBundle, FixtureCredentials, SurfaceAuth, SurfaceSpec } from '../contracts';
import { resolveSurfaceRoute } from './surfaces';

function credentialsForRole(bundle: FixtureBundle, role: Exclude<SurfaceAuth, 'public'>): FixtureCredentials {
  if (role === 'admin') return bundle.users.admin;
  return bundle.users.browser;
}

async function gotoStable(page: Page, path: string) {
  try {
    await page.goto(path);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!/interrupted by another navigation/i.test(message)) {
      throw error;
    }
  }
  await page.waitForLoadState('domcontentloaded');
}

async function performLogin(page: Page, credentials: FixtureCredentials) {
  const response = await page.request.post('/api/auth/login', {
    headers: { 'content-type': 'application/json' },
    data: {
      username: credentials.username,
      password: credentials.password,
    },
  });
  const body = await response.json().catch(() => null);

  expect(response.ok(), `login failed for ${credentials.username}: ${JSON.stringify(body)}`).toBe(true);

  await page.evaluate(() => {
    window.localStorage.setItem('onboarding-done', '1');
    document.cookie = 'logged_in=1; Path=/; Max-Age=604800; SameSite=Lax';
  });
}

export async function loginAsRole(
  page: Page,
  bundle: FixtureBundle,
  role: Exclude<SurfaceAuth, 'public'>,
  redirectPath = '/',
) {
  await gotoStable(page, `/login?redirect=${encodeURIComponent(redirectPath)}`);
  await performLogin(page, credentialsForRole(bundle, role));
  await gotoStable(page, redirectPath);
  await dismissOnboarding(page);
  await page.waitForTimeout(800);
}

export async function openSurface(page: Page, bundle: FixtureBundle, surface: SurfaceSpec) {
  const targetRoute = resolveSurfaceRoute(surface, bundle);

  if (surface.auth === 'public') {
    await gotoStable(page, targetRoute);
    await waitForSettledUi(page);
    return targetRoute;
  }

  await loginAsRole(page, bundle, surface.auth, targetRoute);
  await assertProtectedShell(page);
  return targetRoute;
}
