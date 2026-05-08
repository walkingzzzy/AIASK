import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const appDir = path.join(root, 'app');
const registryPath = path.join(root, 'lib', 'copilot-surface-registry.ts');
const appShellPath = path.join(root, 'components', 'app-shell.tsx');
const source = fs.readFileSync(registryPath, 'utf8');
const appShellSource = fs.readFileSync(appShellPath, 'utf8');

function walk(dir) {
  const items = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) items.push(...walk(full));
    else if (/^page\.(tsx|ts)$/.test(entry.name)) items.push(full);
  }
  return items;
}

function routeFromPage(file) {
  const rel = path.relative(appDir, path.dirname(file));
  if (!rel) return '/';
  return `/${rel.split(path.sep).join('/')}`;
}

function extractObjects(arrayName) {
  const marker = `export const ${arrayName}`;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`Missing ${arrayName}`);
  const equals = source.indexOf('=', start);
  const open = source.indexOf('[', equals);
  let depth = 0;
  let inString = '';
  let escaped = false;
  for (let i = open; i < source.length; i += 1) {
    const ch = source[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === '\\') {
        escaped = true;
      } else if (ch === inString) {
        inString = '';
      }
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      inString = ch;
      continue;
    }
    if (ch === '[') depth += 1;
    if (ch === ']') depth -= 1;
    if (depth === 0) return source.slice(open, i + 1);
  }
  throw new Error(`Cannot parse ${arrayName}`);
}

function extractStringProp(objectText, prop) {
  return objectText.match(new RegExp(`${prop}:\\s*['"]([^'"]+)['"]`))?.[1] ?? '';
}

function extractBooleanProp(objectText, prop) {
  return new RegExp(`${prop}:\\s*true`).test(objectText);
}

function splitTopLevelObjects(arrayText) {
  const objects = [];
  let depth = 0;
  let start = -1;
  let inString = '';
  let escaped = false;
  for (let i = 0; i < arrayText.length; i += 1) {
    const ch = arrayText[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === inString) inString = '';
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      inString = ch;
      continue;
    }
    if (ch === '{') {
      if (depth === 0) start = i;
      depth += 1;
    }
    if (ch === '}') {
      depth -= 1;
      if (depth === 0 && start >= 0) {
        objects.push(arrayText.slice(start, i + 1));
        start = -1;
      }
    }
  }
  return objects;
}

const routeObjects = splitTopLevelObjects(extractObjects('COPILOT_SURFACE_ROUTES'));
const routes = routeObjects.map((objectText) => ({
  pageKey: extractStringProp(objectText, 'pageKey'),
  path: extractStringProp(objectText, 'path'),
  title: extractStringProp(objectText, 'title'),
  public: extractBooleanProp(objectText, 'public'),
  stockAware: extractBooleanProp(objectText, 'stockAware'),
  codeParam: extractStringProp(objectText, 'codeParam'),
  objectText,
}));
const routeByPath = new Map(routes.map((route) => [route.path, route]));
const routeByPageKey = new Map(routes.map((route) => [route.pageKey, route]));
const pageRoutes = walk(appDir).map(routeFromPage).sort();
const publicPaths = new Set(['/login', '/register']);
const errors = [];

for (const routePath of pageRoutes) {
  if (publicPaths.has(routePath)) {
    const route = routeByPath.get(routePath);
    if (!route?.public) errors.push(`${routePath} must be marked public in Copilot surface registry`);
    continue;
  }
  if (!routeByPath.has(routePath)) {
    errors.push(`${routePath} is missing from Copilot surface registry`);
  }
}

for (const route of routes) {
  if (!route.pageKey || !route.path || !route.title) {
    errors.push(`Invalid route entry: ${JSON.stringify(route)}`);
  }
  if (route.stockAware && !route.codeParam) {
    errors.push(`${route.pageKey} is stockAware but missing codeParam`);
  }
  const related = [...route.objectText.matchAll(/relatedPageKeys:\s*\[([\s\S]*?)\]/g)]
    .flatMap((match) => [...match[1].matchAll(/['"]([^'"]+)['"]/g)].map((item) => item[1]));
  for (const key of related) {
    if (!routeByPageKey.has(key)) errors.push(`${route.pageKey} references unknown related pageKey ${key}`);
  }
}

const flowText = extractObjects('COPILOT_TASK_FLOWS');
for (const match of flowText.matchAll(/pageKey:\s*['"]([^'"]+)['"]/g)) {
  if (!routeByPageKey.has(match[1])) errors.push(`Task flow references unknown pageKey ${match[1]}`);
}
for (const match of flowText.matchAll(/nextPageKey:\s*['"]([^'"]+)['"]/g)) {
  if (!routeByPageKey.has(match[1])) errors.push(`Task flow references unknown nextPageKey ${match[1]}`);
}

for (const match of appShellSource.matchAll(/href:\s*['"]([^'"]+)['"]/g)) {
  const href = match[1];
  if (!href.startsWith('/')) continue;
  if (!routeByPath.has(href)) errors.push(`AppShell nav href ${href} is missing from Copilot surface registry`);
}

const fallbackStart = appShellSource.indexOf('const FALLBACK_PAGE_LABELS');
if (fallbackStart >= 0) {
  const fallbackOpen = appShellSource.indexOf('{', fallbackStart);
  let depth = 0;
  let end = -1;
  for (let i = fallbackOpen; i < appShellSource.length; i += 1) {
    const ch = appShellSource[i];
    if (ch === '{') depth += 1;
    if (ch === '}') depth -= 1;
    if (depth === 0) {
      end = i;
      break;
    }
  }
  const fallbackText = appShellSource.slice(fallbackOpen, end + 1);
  for (const match of fallbackText.matchAll(/['"]([^'"]+)['"]:\s*['"]([^'"]+)['"]/g)) {
    const [, routePath, label] = match;
    const route = routeByPath.get(routePath);
    if (!route) {
      errors.push(`AppShell fallback label ${routePath} -> ${label} is missing from Copilot surface registry`);
    } else if (route.title !== label) {
      errors.push(`AppShell fallback label mismatch for ${routePath}: "${label}" vs registry "${route.title}"`);
    }
  }
}

if (errors.length) {
  console.error(`Copilot surface audit failed with ${errors.length} issue(s):`);
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`Copilot surface audit passed: ${pageRoutes.length} page routes, ${routes.length} registry entries.`);
