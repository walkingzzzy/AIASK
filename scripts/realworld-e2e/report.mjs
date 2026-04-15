import fs from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from './shared.mjs';

const CATALOG_PATH = path.join(ROOT, 'apps', 'web', 'e2e', 'realworld', 'catalog.json');

function parseMarkers(title) {
  const surfaceMatch = String(title).match(/\[surface:([^\]]+)\]/);
  const scenarioMatch = String(title).match(/\[scenario:([^\]]+)\]/);
  return {
    surfaceId: surfaceMatch?.[1] || 'unknown',
    scenarioId: scenarioMatch?.[1] || 'unknown',
  };
}

function pickError(result) {
  const firstError = Array.isArray(result?.errors) ? result.errors.find(Boolean) : null;
  return firstError?.message || firstError?.stack || result?.error?.message || null;
}

function relativeTo(rootDir, inputPath) {
  if (!inputPath) return null;
  return path.relative(rootDir, inputPath) || '.';
}

function loadAudit(attachments, outputRoot) {
  const auditAttachment = attachments.find((attachment) => attachment.name === 'runtime-audit' && attachment.path);
  if (!auditAttachment?.path) {
    return null;
  }
  return fs.readFile(auditAttachment.path, 'utf8')
    .then((text) => JSON.parse(text))
    .catch(() => null);
}

async function flattenReportNode(node, outputRoot, rows = [], fallbackBrowser = 'unknown') {
  if (!node || typeof node !== 'object') return rows;

  const specs = Array.isArray(node.specs) ? node.specs : [];
  for (const spec of specs) {
    const tests = Array.isArray(spec.tests) ? spec.tests : [];
    for (const testCase of tests) {
      const title = testCase.title || spec.title || 'unknown';
      const markers = parseMarkers(title);
      const result = Array.isArray(testCase.results) && testCase.results.length > 0
        ? testCase.results[testCase.results.length - 1]
        : {};
      const attachments = Array.isArray(result.attachments)
        ? result.attachments.map((attachment) => ({
            name: attachment.name || 'attachment',
            path: relativeTo(outputRoot, attachment.path),
            contentType: attachment.contentType || null,
            absolutePath: attachment.path || null,
          }))
        : [];
      const audit = await loadAudit(attachments, outputRoot);
      rows.push({
        browser: result.projectName || result.projectId || fallbackBrowser,
        surfaceId: markers.surfaceId,
        scenarioId: markers.scenarioId,
        title,
        status: result.status || 'unknown',
        durationMs: Number(result.duration || 0),
        error: pickError(result),
        failureType: result.status === 'passed'
          ? null
          : audit?.api5xx?.length
            ? 'api5xx'
            : audit?.pageErrors?.length
              ? 'page-error'
              : audit?.consoleErrors?.length
                ? 'console-error'
                : audit?.requestFailures?.length
                  ? 'network'
                  : /timeout/i.test(String(pickError(result) || ''))
                    ? 'timeout'
                    : 'assertion',
        requestSummary: [
          ...(audit?.apiSummary || []),
          ...(audit?.api5xx || []),
          ...(audit?.requestFailures || []),
        ].slice(0, 8),
        consoleSummary: [
          ...(audit?.consoleErrors || []),
          ...(audit?.pageErrors || []),
        ].slice(0, 8),
        route: audit?.route || '',
        auth: audit?.auth || 'public',
        attachments: attachments.map(({ absolutePath, ...attachment }) => attachment),
      });
    }
  }

  const suites = Array.isArray(node.suites) ? node.suites : [];
  for (const suite of suites) {
    await flattenReportNode(suite, outputRoot, rows, fallbackBrowser);
  }
  return rows;
}

async function loadBrowserMeta(outputDir) {
  try {
    const metaPath = path.join(outputDir, 'browser-meta.json');
    return JSON.parse(await fs.readFile(metaPath, 'utf8'));
  } catch {
    return null;
  }
}

function escapeCsv(value) {
  const text = String(value ?? '');
  if (!/[",\n]/.test(text)) {
    return text;
  }
  return `"${text.replace(/"/g, '""')}"`;
}

function summarizeByBrowser(rows) {
  const map = new Map();
  for (const row of rows) {
    const current = map.get(row.browser) || { passed: 0, failed: 0, total: 0, durationMs: 0 };
    current.total += 1;
    current.durationMs += Number(row.durationMs || 0);
    if (row.status === 'passed') current.passed += 1;
    else current.failed += 1;
    map.set(row.browser, current);
  }
  return Array.from(map.entries()).map(([browser, summary]) => ({ browser, ...summary }));
}

export async function aggregateRealworldReports(outputRoot, browserResults, meta) {
  const catalog = JSON.parse(await fs.readFile(CATALOG_PATH, 'utf8'));
  const catalogMap = new Map(catalog.map((surface) => [surface.surfaceId, surface]));
  const allRows = [];
  const startupFailures = [];

  for (const result of browserResults) {
    if (!result.playwrightJsonPath) continue;
    const browserMeta = await loadBrowserMeta(result.outputDir);
    try {
      const report = JSON.parse(await fs.readFile(result.playwrightJsonPath, 'utf8'));
      const rows = await flattenReportNode(report, outputRoot, [], result.browser);
      for (const row of rows) {
        const surface = catalogMap.get(row.surfaceId);
        if (surface) {
          row.route = surface.route;
          row.auth = surface.auth;
          row.mutationRisk = surface.mutationRisk;
        }
      }
      allRows.push(...rows);
    } catch (error) {
      startupFailures.push({
        browser: result.browser,
        error: browserMeta?.error || String(error instanceof Error ? error.stack || error.message : error),
        status: browserMeta?.status || 'failed',
      });
      const errorPath = path.join(result.outputDir, 'report-parse-error.txt');
      await fs.writeFile(errorPath, String(error instanceof Error ? error.stack || error.message : error), 'utf8');
    }
  }

  const matrixJsonPath = path.join(outputRoot, 'matrix.json');
  const matrixCsvPath = path.join(outputRoot, 'matrix.csv');
  const summaryPath = path.join(outputRoot, 'summary.md');
  const failuresPath = path.join(outputRoot, 'failures.md');
  const uniqueSurfaces = new Set(allRows.map((row) => row.surfaceId));
  const failedRows = allRows.filter((row) => row.status !== 'passed');
  const browserSummary = summarizeByBrowser(allRows);

  await fs.writeFile(matrixJsonPath, JSON.stringify(allRows, null, 2), 'utf8');
  await fs.writeFile(
    matrixCsvPath,
    [
      'browser,surfaceId,scenarioId,status,durationMs,failureType,error,route,auth',
      ...allRows.map((row) => [
        escapeCsv(row.browser),
        escapeCsv(row.surfaceId),
        escapeCsv(row.scenarioId),
        escapeCsv(row.status),
        escapeCsv(row.durationMs),
        escapeCsv(row.failureType || ''),
        escapeCsv(row.error || ''),
        escapeCsv(row.route || ''),
        escapeCsv(row.auth || ''),
      ].join(',')),
    ].join('\n'),
    'utf8',
  );

  const summaryLines = [
    '# AIASK 前端 54 页面真实联调测试报告',
    '',
    `- Run ID: ${meta.runId}`,
    `- 执行时间: ${meta.startedAt} -> ${meta.endedAt}`,
    `- 专用环境: ${meta.envName}`,
    `- 浏览器批次: ${browserResults.map((item) => item.browser).join(', ')}`,
    `- 覆盖对象: ${uniqueSurfaces.size}/54`,
    `- 场景总数: ${allRows.length}`,
    `- 失败场景: ${failedRows.length}`,
    `- 启动/seed 失败浏览器批次: ${startupFailures.length}`,
    '',
    '## Browser Summary',
    '',
    ...browserSummary.map((item) => `- ${item.browser}: passed=${item.passed}, failed=${item.failed}, total=${item.total}, duration_ms=${item.durationMs}`),
    ...(browserSummary.length ? [''] : []),
    '## Browser Startup Failures',
    '',
    ...(startupFailures.length
      ? startupFailures.map((item) => `- ${item.browser}: ${String(item.error || item.status || 'startup failure').split('\n')[0]}`)
      : ['- 无启动级失败']),
    '',
    '## Artifacts',
    '',
    '- [matrix.json](./matrix.json)',
    '- [matrix.csv](./matrix.csv)',
    '- [failures.md](./failures.md)',
    ...browserResults.flatMap((item) => ([
      `- [${item.browser} Playwright HTML](./${path.relative(outputRoot, item.playwrightHtmlDir)}/index.html)`,
    ])),
    '',
    '## Failure Highlights',
    '',
    ...(failedRows.length
      ? failedRows.slice(0, 20).map((row) => `- ${row.browser} / ${row.surfaceId} / ${row.scenarioId}: ${String(row.error || row.failureType || 'unknown failure').split('\n')[0]}`)
      : ['- 无失败场景']),
    '',
  ];
  await fs.writeFile(summaryPath, summaryLines.join('\n'), 'utf8');

  const failureLines = [
    '# AIASK 前端失败清单',
    '',
  ];

  if (!failedRows.length) {
    failureLines.push('- 本次运行没有失败场景。');
  } else {
    for (const row of failedRows) {
      const attachments = row.attachments || [];
      const screenshot = attachments.find((attachment) => /screenshot/i.test(attachment.name));
      const trace = attachments.find((attachment) => /trace/i.test(attachment.name));
      const video = attachments.find((attachment) => /video/i.test(attachment.name));

      failureLines.push(`## ${row.browser} / ${row.surfaceId} / ${row.scenarioId}`);
      failureLines.push(`- 失败类型: ${row.failureType || 'unknown'}`);
      failureLines.push(`- 路由对象: ${row.route || '-'}`);
      failureLines.push(`- 主要报错: ${String(row.error || 'unknown').split('\n')[0]}`);
      failureLines.push(`- 请求摘要: ${(row.requestSummary || []).join(' | ') || '-'}`);
      failureLines.push(`- Console 摘要: ${(row.consoleSummary || []).join(' | ') || '-'}`);
      failureLines.push(`- 截图: ${screenshot?.path ? `[${screenshot.name}](./${screenshot.path})` : '-'}`);
      failureLines.push(`- Trace: ${trace?.path ? `[${trace.name}](./${trace.path})` : '-'}`);
      failureLines.push(`- 视频: ${video?.path ? `[${video.name}](./${video.path})` : '-'}`);
      failureLines.push('- 复现步骤:');
      failureLines.push(`1. 运行 \`node scripts/realworld-e2e/run.mjs --browser ${row.browser}\`.`);
      failureLines.push(`2. 进入对象 \`${row.surfaceId}\` 对应路由 \`${row.route || '-'}\`。`);
      failureLines.push(`3. 执行场景 \`${row.scenarioId}\` 并比对请求/console 摘要。`);
      failureLines.push('');
    }
  }

  if (startupFailures.length) {
    failureLines.push('## 启动级失败');
    failureLines.push('');
    for (const item of startupFailures) {
      failureLines.push(`### ${item.browser}`);
      failureLines.push(`- 失败类型: startup`);
      failureLines.push(`- 主要报错: ${String(item.error || item.status || 'startup failure').split('\n')[0]}`);
      failureLines.push(`- 复现步骤:`);
      failureLines.push(`1. 运行 \`node scripts/realworld-e2e/run.mjs --browser ${item.browser}\`.`);
      failureLines.push(`2. 检查对应浏览器目录下的 \`browser-meta.json\`、服务日志与 seed 日志。`);
      failureLines.push('');
    }
  }

  await fs.writeFile(failuresPath, failureLines.join('\n'), 'utf8');

  return {
    rowCount: allRows.length,
    failedCount: failedRows.length,
    uniqueSurfaceCount: uniqueSurfaces.size,
  };
}
