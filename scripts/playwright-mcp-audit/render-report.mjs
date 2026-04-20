import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = {
    outputDir: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

async function readJsonIfExists(filePath, fallback) {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

async function readTextIfExists(filePath, fallback = '') {
  try {
    return await fs.readFile(filePath, 'utf8');
  } catch {
    return fallback;
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function truncateText(value, limit = 220) {
  const normalized = normalizeText(value);
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, limit - 1)}…`;
}

function relativeFrom(baseDir, absolutePath) {
  return path.relative(baseDir, absolutePath).split(path.sep).join('/');
}

function loadMarkedPayloads(rawConsole) {
  return rawConsole
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.includes('__PW_AUDIT_RESULTS__'))
    .flatMap((line) => {
      const index = line.indexOf('__PW_AUDIT_RESULTS__');
      if (index < 0) return [];
      const payload = line.slice(index + '__PW_AUDIT_RESULTS__'.length);
      try {
        return [JSON.parse(payload)];
      } catch {
        return [];
      }
    });
}

function collectTests(node, rows = []) {
  if (!node || typeof node !== 'object') {
    return rows;
  }

  const specs = Array.isArray(node.specs) ? node.specs : [];
  for (const spec of specs) {
    const tests = Array.isArray(spec.tests) ? spec.tests : [];
    for (const testCase of tests) {
      const title = [spec.title, testCase.title].filter(Boolean).join(' / ');
      const results = Array.isArray(testCase.results) ? testCase.results : [];
      const finalResult = results.length ? results[results.length - 1] : {};
      rows.push({
        title,
        status: finalResult.status || 'unknown',
        error: finalResult.error?.message
          || finalResult.errors?.find(Boolean)?.message
          || null,
      });
    }
  }

  const suites = Array.isArray(node.suites) ? node.suites : [];
  for (const suite of suites) {
    collectTests(suite, rows);
  }

  return rows;
}

function buildTestMatcher(manifest) {
  const functionalBundles = [
    {
      pattern: /market, search and stock analysis/i,
      surfaces: ['market', 'stock', 'search'],
    },
    {
      pattern: /macro, options and data-center/i,
      surfaces: ['macro', 'options', 'data'],
    },
    {
      pattern: /notifications, settings and admin utility/i,
      surfaces: [
        'notifications',
        'settings',
        'settings-security',
        'settings-audit-log',
        'admin-cache',
        'admin-tools',
        'admin-dead-letters',
        'admin-users',
      ],
    },
  ];

  const directMatchers = manifest.surfaces.map((surface) => ({
    pattern: new RegExp(`${escapeRegExp(surface.label)}|${escapeRegExp(surface.surfaceId)}|${escapeRegExp(surface.route.replace(/:[^/]+/g, ''))}`),
    surfaces: [surface.surfaceId],
  }));

  return [...functionalBundles, ...directMatchers];
}

function mapTestsToSurfaces(tests, manifest) {
  const matcher = buildTestMatcher(manifest);
  const bySurface = new Map();

  for (const test of tests) {
    const title = normalizeText(test.title);
    for (const entry of matcher) {
      if (!entry.pattern.test(title)) continue;
      for (const surfaceId of entry.surfaces) {
        const bucket = bySurface.get(surfaceId) || [];
        bucket.push(test);
        bySurface.set(surfaceId, bucket);
      }
    }
  }

  return bySurface;
}

function buildVisualAssessment(surface, result) {
  const buttonCount = Array.isArray(result?.buttons) ? result.buttons.length : 0;
  const tabCount = Array.isArray(result?.tabs) ? result.tabs.length : 0;
  const fieldCount = Array.isArray(result?.fields) ? result.fields.length : 0;
  const headings = Array.isArray(result?.headings) ? result.headings.length : 0;
  const modules = Array.isArray(result?.sections) ? result.sections.length : 0;

  const lines = [];
  if (modules >= 4 || tabCount >= 4) {
    lines.push('这是典型的工作台式页面，模块并列较多，信息密度偏高，首屏需要更清晰的主次层级。');
  } else if (fieldCount >= 4) {
    lines.push('页面以表单和参数输入为主，任务聚焦明确，但提交前后的状态反馈需要足够直接。');
  } else if (buttonCount >= 10) {
    lines.push('操作入口较密集，按钮层级已经接近过载，次级动作与高风险动作需要更明显区分。');
  } else {
    lines.push('页面结构相对直接，入口路径清晰，适合作为单功能或轻工作流页面。');
  }

  if (headings <= 1 && modules <= 2) {
    lines.push('视觉层级比较单薄，建议加强标题、副标题和结果区域之间的分组感。');
  }

  if ((result?.issues?.consoleErrors?.length || 0) > 0 || (result?.issues?.apiErrors?.length || 0) > 0) {
    lines.push('存在运行时噪音时，会削弱页面稳定感，建议先压低 console/API 异常再谈视觉打磨。');
  }

  if (surface.group === 'admin') {
    lines.push('后台页面更偏运维工具，建议强化危险操作区域的隔离和确认层次。');
  }

  return lines.slice(0, 3);
}

function buildIssueList(surface, result, tests) {
  const issues = [];
  const controls = Array.isArray(result?.buttons) ? result.buttons : [];
  const failedControls = controls.filter((control) => ['failed', 'blocked'].includes(control.status));
  const partialControls = controls.filter((control) => control.status === 'partial');

  for (const control of failedControls.slice(0, 5)) {
    issues.push(`控件“${control.label}”在 ${control.context || '当前页面'} 中未成功走通：${control.note || '点击后没有得到预期反馈'}`);
  }
  for (const control of partialControls.slice(0, 3)) {
    issues.push(`控件“${control.label}”只达到了部分预期：${control.note || '需要人工进一步确认'}`);
  }
  for (const error of (result?.issues?.apiErrors || []).slice(0, 3)) {
    issues.push(`接口异常：${truncateText(error)}`);
  }
  for (const error of (result?.issues?.consoleErrors || []).slice(0, 3)) {
    issues.push(`前端异常：${truncateText(error)}`);
  }
  for (const test of tests.filter((item) => item.status !== 'passed').slice(0, 3)) {
    issues.push(`自动化测试未通过：${test.title}${test.error ? ` (${truncateText(test.error, 140)})` : ''}`);
  }

  if (!issues.length && result?.status === 'blocked') {
    issues.push('当前页面因数据、权限或上游服务原因阻塞，未能完成完整闭环验证。');
  }

  return issues.slice(0, 8);
}

function buildRecommendations(surface, result) {
  const recommendations = [];
  const buttonCount = Array.isArray(result?.buttons) ? result.buttons.length : 0;
  const failedCount = (result?.buttons || []).filter((item) => item.status === 'failed').length;

  if (buttonCount >= 10) {
    recommendations.push('压缩次级按钮数量，把主要任务路径收敛到 1 到 3 个高优先级动作。');
  }
  if (failedCount > 0 || (result?.issues?.apiErrors?.length || 0) > 0) {
    recommendations.push('先清理接口失败和运行时异常，再做视觉和交互层优化，否则页面可信度会持续受损。');
  }
  if (surface.mutationRisk === 'high') {
    recommendations.push('高风险操作建议补齐二次确认、结果回执和可回滚提示，避免误触影响真实数据。');
  }
  if ((result?.workflow || []).length === 0) {
    recommendations.push('为页面补一条明确的端到端任务路径，让用户能从首屏直接到达“输入-执行-结果”闭环。');
  } else {
    recommendations.push('把已存在的流程结果区做成更明确的成功/失败状态面板，降低用户复盘成本。');
  }
  if (surface.group === 'auth' || surface.surfaceId.startsWith('settings')) {
    recommendations.push('账户与安全页面建议强化步骤说明和状态回执，减少用户对账号状态变化的焦虑。');
  }

  return recommendations.slice(0, 4);
}

function summarizeControls(result) {
  const controls = Array.isArray(result?.buttons) ? result.buttons : [];
  return controls.map((control) => `- ${control.label} [${control.status}]${control.context ? ` (${control.context})` : ''}${control.note ? `：${control.note}` : ''}`);
}

function summarizeWorkflow(result) {
  const workflow = Array.isArray(result?.workflow) ? result.workflow : [];
  return workflow.map((step) => `- ${step.name} [${step.status}]${step.note ? `：${step.note}` : ''}`);
}

async function renderSurfaceReport(baseDir, surface, result, tests) {
  const surfaceDir = path.join(baseDir, surface.group, surface.surfaceId);
  const reportPath = path.join(surfaceDir, 'report.md');
  await fs.mkdir(surfaceDir, { recursive: true });

  const screenshots = Array.isArray(result?.screenshots) ? result.screenshots : [];
  const screenshotLines = screenshots.length
    ? screenshots.map((filePath) => `- [${path.basename(filePath)}](./${relativeFrom(surfaceDir, filePath)})`)
    : ['- 无截图产物'];
  const testLines = tests.length
    ? tests.slice(0, 8).map((test) => `- ${test.title} [${test.status}]${test.error ? `：${truncateText(test.error, 140)}` : ''}`)
    : ['- 本页没有匹配到现成 Playwright 自动化用例'];
  const issueLines = buildIssueList(surface, result, tests);
  const recommendationLines = buildRecommendations(surface, result);
  const layoutLines = buildVisualAssessment(surface, result);
  const controlLines = summarizeControls(result);
  const workflowLines = summarizeWorkflow(result);

  const content = [
    `# ${surface.label}`,
    '',
    '## 页面概览',
    '',
    `- Surface ID: \`${surface.surfaceId}\``,
    `- 路由: \`${surface.route}\``,
    `- 鉴权: \`${surface.auth}\``,
    `- 分组: \`${surface.group}\``,
    `- 页面状态: \`${result?.status || 'missing'}\``,
    `- 页面标题: ${result?.title || '-'}`,
    `- 最终地址: ${result?.finalUrl || '-'}`,
    `- 主要标题: ${(result?.headings || []).join(' | ') || '-'}`,
    `- 主要分区: ${(result?.sections || []).join(' | ') || '-'}`,
    '',
    '## 截图',
    '',
    ...screenshotLines,
    '',
    '## 视觉设计与布局',
    '',
    ...layoutLines.map((line) => `- ${line}`),
    '',
    '## 功能与流程',
    '',
    ...(workflowLines.length ? workflowLines : ['- 本页未执行专用 workflow，主要依赖逐控件审查和路由 smoke。']),
    '',
    '## 按钮与交互实测',
    '',
    ...(controlLines.length ? controlLines : ['- 未采集到稳定可见按钮，或页面主要由静态内容组成。']),
    '',
    '## 自动化验证证据',
    '',
    ...testLines,
    '',
    '## 运行时异常',
    '',
    ...((result?.issues?.apiErrors || []).slice(0, 5).map((line) => `- API: ${truncateText(line)}`)),
    ...((result?.issues?.consoleErrors || []).slice(0, 5).map((line) => `- Console: ${truncateText(line)}`)),
    ...((result?.issues?.requestFailures || []).slice(0, 5).map((line) => `- Request: ${truncateText(line)}`)),
    ...((result?.issues?.apiErrors || []).length || (result?.issues?.consoleErrors || []).length || (result?.issues?.requestFailures || []).length ? [] : ['- 未记录到明显运行时异常']),
    '',
    '## 问题列表',
    '',
    ...(issueLines.length ? issueLines.map((line) => `- ${line}`) : ['- 本页未发现明确功能性阻塞，主要风险集中在状态反馈和信息密度。']),
    '',
    '## 修改与优化建议',
    '',
    ...recommendationLines.map((line) => `- ${line}`),
    '',
  ].join('\n');

  await fs.writeFile(reportPath, content, 'utf8');
  return reportPath;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const outputDir = args.outputDir;
  const manifest = await readJsonIfExists(path.join(outputDir, 'raw', 'surface-manifest.json'), { surfaces: [] });
  const crawlJson = await readJsonIfExists(path.join(outputDir, 'raw', 'mcp-crawl-results.json'), null);
  const crawlConsole = await readTextIfExists(path.join(outputDir, 'raw', 'mcp-console.log'));
  const crawlPayloads = crawlJson
    ? [crawlJson]
    : loadMarkedPayloads(crawlConsole);

  const crawlResults = new Map();
  for (const payload of crawlPayloads) {
    const items = Array.isArray(payload?.results) ? payload.results : Array.isArray(payload) ? payload : [];
    for (const item of items) {
      crawlResults.set(item.surfaceId, item);
    }
  }

  const playwrightFiles = [
    path.join(outputDir, 'playwright', 'sitewide-pages-user.json'),
    path.join(outputDir, 'playwright', 'sitewide-pages-admin.json'),
    path.join(outputDir, 'playwright', 'button-sweep-user.json'),
    path.join(outputDir, 'playwright', 'button-sweep-admin.json'),
    path.join(outputDir, 'playwright', 'sitewide-functional-user.json'),
    path.join(outputDir, 'playwright', 'sitewide-functional-admin.json'),
    path.join(outputDir, 'playwright', 'core-flows-user.json'),
    path.join(outputDir, 'playwright', 'core-flows-admin.json'),
  ];

  const allTests = [];
  for (const filePath of playwrightFiles) {
    const payload = await readJsonIfExists(filePath, null);
    if (payload) {
      collectTests(payload, allTests);
    }
  }
  const testsBySurface = mapTestsToSurfaces(allTests, manifest);

  const reportRows = [];
  for (const surface of manifest.surfaces) {
    const result = crawlResults.get(surface.surfaceId) || {
      surfaceId: surface.surfaceId,
      status: 'missing',
      issues: {},
      buttons: [],
      workflow: [],
      screenshots: [],
      headings: [],
      sections: [],
    };
    const tests = testsBySurface.get(surface.surfaceId) || [];
    const reportPath = await renderSurfaceReport(outputDir, surface, result, tests);
    reportRows.push({
      surfaceId: surface.surfaceId,
      label: surface.label,
      group: surface.group,
      auth: surface.auth,
      status: result.status || 'missing',
      reportPath,
      issueCount: buildIssueList(surface, result, tests).length,
    });
  }

  const passed = reportRows.filter((row) => row.status === 'passed').length;
  const blocked = reportRows.filter((row) => row.status === 'blocked').length;
  const failed = reportRows.filter((row) => row.status === 'failed' || row.status === 'missing').length;
  const highRisk = manifest.surfaces.filter((surface) => surface.mutationRisk === 'high').length;

  const summaryLines = [
    '# Playwright MCP 全量页面审查总报告',
    '',
    `- 生成时间: ${new Date().toISOString()}`,
    `- 页面总数: ${manifest.total || manifest.surfaces.length}`,
    `- 通过: ${passed}`,
    `- 阻塞: ${blocked}`,
    `- 失败/缺失: ${failed}`,
    `- 高风险页面数: ${highRisk}`,
    '',
    '## 覆盖矩阵',
    '',
    ...reportRows.map((row) => `- [${row.label}](./${relativeFrom(outputDir, row.reportPath)}) | \`${row.status}\` | group=\`${row.group}\` | auth=\`${row.auth}\` | issues=${row.issueCount}`),
    '',
    '## 关键问题 Top',
    '',
    ...reportRows
      .sort((left, right) => right.issueCount - left.issueCount)
      .slice(0, 10)
      .map((row) => `- ${row.label}: status=${row.status}, issues=${row.issueCount}`),
    '',
    '## 原始产物',
    '',
    '- [surface-manifest.json](./raw/surface-manifest.json)',
    '- [mcp-console.log](./raw/mcp-console.log)',
    '- [mcp-crawl-results.json](./raw/mcp-crawl-results.json)',
    '',
  ].join('\n');

  await fs.writeFile(path.join(outputDir, 'index.md'), summaryLines, 'utf8');
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
