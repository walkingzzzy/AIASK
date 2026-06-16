import { expect, type Page } from "@playwright/test";
import {
  controlLabel,
  expectedTextLabel,
  tabLabel,
  viewLabel,
  waitForMainViewReady,
} from "./capabilitiesNavigation";
export interface FrontendControl {
  tag: string;
  name: string;
  disabled: boolean;
  placeholder: string;
  className: string;
  outerHTML: string;
  parentText: string;
  rect: { x: number; y: number; width: number; height: number };
}

export interface FrontendInventory {
  page: string;
  viewport: string;
  headings: string[];
  controls: FrontendControl[];
  summary: {
    controlCount: number;
    buttonCount: number;
    inputCount: number;
    disabledCount: number;
    overflowX: boolean;
    mojibakeCount: number;
    textOverflow: Array<{ tag: string; text: string; scrollWidth: number; clientWidth: number }>;
    nestedCardCount: number;
    sidebarMainOverlap: boolean;
    oversizedRadius: Array<{ tag: string; text: string; radius: string }>;
    tinyButtons: string[];
  };
}

export interface MatrixReport {
  generated_at: string;
  mode: "mock_safe";
  command_results: string[];
  pages: FrontendInventory[];
  actions: Array<{ page: string; control: string; result: string; note?: string }>;
  gated: Array<{ page: string; control: string; result: string; note?: string }>;
  layout: Array<{ page: string; viewport: string; status: string; checks: FrontendInventory["summary"] }>;
  screenshots: string[];
  assumptions: string[];
}

function uniqueNames(items: FrontendControl[]): string[] {
  return Array.from(new Set(items.map((item) => item.name).filter(Boolean))).sort();
}

export async function collectMainInventory(page: Page, pageName: string): Promise<FrontendInventory> {
  return page.locator("body").evaluate((body, label) => {
    const visible = (element: Element) => {
      const closedDetails = element.closest("details:not([open])");
      if (closedDetails && !element.closest("summary")) return false;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
    };
    const textOf = (element: Element) => {
      const input = element as HTMLInputElement;
      const labelled = "labels" in input && input.labels?.[0] ? input.labels[0].innerText : "";
      return (
        element.getAttribute("aria-label") ||
        element.getAttribute("title") ||
        labelled ||
        (element as HTMLElement).innerText ||
        input.value ||
        input.placeholder ||
        input.name ||
        input.id ||
        element.tagName
      )
        .replace(/\s+/g, " ")
        .trim();
    };
    const overlayBody = body.querySelector(".overlay-view .overlay-surface-body");
    const overlayActive = Boolean(overlayBody && visible(overlayBody));
    const workspace = overlayActive ? overlayBody as Element : body.querySelector("main") || body;
    const controls = Array.from(workspace.querySelectorAll("button,input,textarea,select,a,[role='button'],[role='tab']"))
      .filter(visible)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const input = element as HTMLInputElement;
        return {
        tag: element.tagName.toLowerCase(),
        name: textOf(element).slice(0, 140),
        disabled: Boolean(input.disabled) || element.getAttribute("aria-disabled") === "true",
        placeholder: input.placeholder || "",
        className: String((element as HTMLElement).className || ""),
        outerHTML: (element as HTMLElement).outerHTML.slice(0, 260),
        parentText: ((element.parentElement as HTMLElement | null)?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 260),
        rect: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
            height: Math.round(rect.height)
          }
        };
      });
    const headings = Array.from(workspace.querySelectorAll("h1,h2,h3"))
      .filter(visible)
      .map((heading) => (heading as HTMLElement).innerText.replace(/\s+/g, " ").trim())
      .slice(0, 12);
    const bodyText = workspace.textContent || "";
    const mojibakeCount = ["锟", "�", "脙", "脗", "閿", "焲", "莽", "猫", "茅"].reduce(
      (count, marker) => count + bodyText.split(marker).length - 1,
      0
    );
    const textOverflow = Array.from(workspace.querySelectorAll("button,.capability-section,.metric-card,.field-row,.settings-row,.job-row,.tool-row,.event-card"))
      .filter(visible)
      .filter((element) => (element as HTMLElement).scrollWidth > (element as HTMLElement).clientWidth + 2)
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        text: textOf(element).slice(0, 120),
        scrollWidth: (element as HTMLElement).scrollWidth,
        clientWidth: (element as HTMLElement).clientWidth
      }))
      .slice(0, 20);
    const nestedCardCount = Array.from(workspace.querySelectorAll(".capability-section .capability-section, .metric-card .metric-card, .card .card")).filter(visible).length;
    const sidebar = body.querySelector(".sidebar");
    const workspaceRect = workspace.getBoundingClientRect();
    const sidebarRect = sidebar?.getBoundingClientRect();
    const sidebarMainOverlap = !overlayActive && Boolean(
      sidebarRect &&
        sidebarRect.width > 0 &&
        workspaceRect.width > 0 &&
        workspaceRect.left < sidebarRect.right - 1 &&
        workspaceRect.right > sidebarRect.left + 1 &&
        workspaceRect.top < sidebarRect.bottom - 1 &&
        workspaceRect.bottom > sidebarRect.top + 1
    );
    const oversizedRadius = Array.from(workspace.querySelectorAll("button,.capability-section,.metric-card,.capability-card,.event-card,.job-row"))
      .filter(visible)
      .map((element) => ({ element, radius: getComputedStyle(element).borderRadius }))
      .filter(({ radius }) => parseFloat(radius) > 12)
      .map(({ element, radius }) => ({ tag: element.tagName.toLowerCase(), text: textOf(element).slice(0, 100), radius }))
      .slice(0, 20);
    const tinyButtons = controls
      .filter((control) => control.tag === "button" && (control.rect.width < 28 || control.rect.height < 24))
      .map((control) => control.name);
    return {
      page: label,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      headings,
      controls,
      summary: {
        controlCount: controls.length,
        buttonCount: controls.filter((control) => control.tag === "button" || control.tag === "a").length,
        inputCount: controls.filter((control) => ["input", "textarea", "select"].includes(control.tag)).length,
        disabledCount: controls.filter((control) => control.disabled).length,
        overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
        mojibakeCount,
        textOverflow,
        nestedCardCount,
        sidebarMainOverlap,
        oversizedRadius,
        tinyButtons
      }
    };
  }, pageName);
}

export function expectCleanInventory(inventory: FrontendInventory) {
  expect(inventory.headings.length, `${inventory.page} should expose visible headings`).toBeGreaterThan(0);
  expect(inventory.summary.overflowX, `${inventory.page} has horizontal overflow`).toBe(false);
  expect(inventory.summary.mojibakeCount, `${inventory.page} has mojibake text`).toBe(0);
  expect(inventory.summary.textOverflow, `${inventory.page} has clipped text`).toEqual([]);
  expect(inventory.summary.nestedCardCount, `${inventory.page} nests cards inside cards`).toBe(0);
  expect(inventory.summary.sidebarMainOverlap, `${inventory.page} sidebar overlaps main workspace`).toBe(false);
  expect(inventory.summary.oversizedRadius, `${inventory.page} uses oversized operational card/button radii`).toEqual([]);
  expect(inventory.summary.tinyButtons, `${inventory.page} has too-small buttons`).toEqual([]);
}

export function assertMainButtonCoverage(
  inventory: FrontendInventory,
  covered: string[],
  options: { structural?: string[]; gated?: string[]; allowedPrefixes?: string[] } = {}
) {
  const allowed = new Set(
    [...covered, ...(options.structural || []), ...(options.gated || [])].flatMap((name) => [
      name,
      controlLabel(name),
      tabLabel(name),
      viewLabel(name)
    ])
  );
  const allowedPrefixes = (options.allowedPrefixes || []).flatMap((prefix) => [
    prefix,
    controlLabel(prefix),
    tabLabel(prefix),
    viewLabel(prefix)
  ]);
  const visibleButtonControls = inventory.controls.filter((control) => control.tag === "button" || control.tag === "a");
  const visibleButtonNames = uniqueNames(visibleButtonControls);
  const missing = visibleButtonNames
    .filter((name) => !allowed.has(name) && !allowedPrefixes.some((prefix) => name.startsWith(prefix)))
    .map((name) => {
      const control = visibleButtonControls.find((item) => item.name === name);
      return {
        name,
        className: control?.className || "",
        outerHTML: control?.outerHTML || "",
        parentText: control?.parentText || "",
        rect: control?.rect,
      };
    });
  expect(missing, `${inventory.page} has visible buttons without matrix classification`).toEqual([]);
}

export async function recordInventory(report: MatrixReport, page: Page, pageName: string) {
  await waitForMainViewReady(page, pageName);
  const inventory = await collectMainInventory(page, pageName);
  expectCleanInventory(inventory);
  report.pages.push(inventory);
  report.layout.push({ page: pageName, viewport: inventory.viewport, status: "passed", checks: inventory.summary });
  return inventory;
}

export async function clickAndRecord(
  report: MatrixReport,
  page: Page,
  pageName: string,
  buttonName: string,
  expectedText?: string,
  scope = page.locator("body")
) {
  const actualName = controlLabel(buttonName);
  const button = scope.getByRole("button", { name: actualName, exact: true });
  await expect(button, `${pageName} ${buttonName} should resolve once`).toHaveCount(1);
  await expect(button, `${pageName} ${buttonName} should be enabled`).toBeEnabled();
  await button.click();
  if (expectedText) {
    const visibleExpectedText = expectedTextLabel(expectedText);
    await expect
      .poll(async () => page.locator("body").evaluate((body) => (body as HTMLElement).innerText), {
        message: `${pageName} should show ${visibleExpectedText}`,
        timeout: 7_500
      })
      .toContain(visibleExpectedText);
  }
  report.actions.push({ page: pageName, control: buttonName, result: "clicked", note: expectedText });
}

export async function expectDisabledAndRecord(report: MatrixReport, page: Page, pageName: string, buttonName: string, note?: string) {
  const actualName = controlLabel(buttonName);
  const button = page.getByRole("button", { name: actualName, exact: true });
  await expect(button, `${pageName} ${buttonName} should resolve once`).toHaveCount(1);
  await expect(button, `${pageName} ${buttonName} should be disabled`).toBeDisabled();
  report.gated.push({ page: pageName, control: buttonName, result: "disabled", note });
}
