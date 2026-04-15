import { expect, type Locator, type Page } from '@playwright/test';

export async function expectAnyVisible(locators: Locator[], timeout = 20_000) {
  await expect
    .poll(async () => {
      for (const locator of locators) {
        const count = await locator.count().catch(() => 0);
        for (let index = 0; index < count; index += 1) {
          if (await locator.nth(index).isVisible().catch(() => false)) {
            return true;
          }
        }
      }
      return false;
    }, { timeout, intervals: [250, 500, 1_000] })
    .toBe(true);
}

export async function expectTextAny(page: Page, patterns: Array<string | RegExp>, timeout = 20_000) {
  await expectAnyVisible(
    patterns.map((pattern) => page.getByText(pattern).first()),
    timeout,
  );
}

export async function clickVisibleTab(page: Page, names: Array<string | RegExp>) {
  for (const name of names) {
    const tab = page.getByRole('tab', { name }).first();
    if (await tab.isVisible().catch(() => false)) {
      await tab.click();
      return;
    }
  }
  throw new Error(`unable to find visible tab: ${names.map(String).join(', ')}`);
}
