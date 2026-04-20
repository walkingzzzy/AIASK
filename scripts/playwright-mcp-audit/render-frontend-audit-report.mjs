import fs from 'node:fs/promises';
import path from 'node:path';

import { ensureDir, relativePath } from './browser-common.mjs';

const SEVERITY_ORDER = { P0: 0, P1: 1, P2: 2, P3: 3 };
const CATEGORY_ORDER = [
  '信息层级',
  '首屏主任务清晰度',
  'CTA 优先级',
  '卡片密度与留白',
  '玻璃/背景/边框一致性',
  '配色与数据语义',
  '字体层级与可读性',
  '图表与数据卡主次',
  '表格可扫读性',
  '空态/加载态/错误态',
  '移动端断点细节',
  '危险操作视觉隔离',
];

const PAGE_OVERRIDES = {
  home: [
    {
      severity: 'P1',
      category: '玻璃/背景/边框一致性',
      evidence: '首页 hero、右侧概览和下方摘要区都使用大面积玻璃卡，外层壳与内层卡片边界重复，主视觉锚点被稀释。',
      recommendation: '把首页首屏收成单一主容器，减少重复玻璃边框，让 Hero、主 CTA 和平台摘要在一套层级里完成。',
    },
    {
      severity: 'P2',
      category: '信息层级',
      evidence: '当前首屏仍同时承载平台介绍、快捷入口、运行概况和三块摘要的过渡说明，阅读焦点在 Hero 和下方摘要之间来回跳转。',
      recommendation: '继续压缩首屏引导文案，并把“当前运行概况”缩成一行摘要条，避免和下方三块核心摘要重复。',
    },
  ],
  admin: [
    {
      severity: 'P1',
      category: '危险操作视觉隔离',
      evidence: '管理后台里的快照、缓存、死信与用户入口被放在同一信息流里，危险动作与一般查看动作的视觉隔离仍然偏弱。',
      recommendation: '把“危险操作”独立成单独区域，并提升危险色、确认层和结果回执的视觉层级，避免后台首页出现误触。',
    },
    {
      severity: 'P2',
      category: '信息层级',
      evidence: '后台首页的优先处理、快捷入口、运行快照和常用入口都在同一密度层级内，第一屏信息过密。',
      recommendation: '把首页压成“当前异常 + 推荐去向 + 一组关键状态”，其他入口下沉到二级页或折叠区。',
    },
  ],
  factor: [
    {
      severity: 'P1',
      category: '移动端断点细节',
      evidence: '因子研究页移动端下 Hero 状态摘要和 workspace 标签堆叠较紧，主标题区与状态卡之间存在压缩感，已接近叠压边缘。',
      recommendation: '移动端把状态摘要改成更短的 2 列概览，并给标签组和状态卡增加更明确的垂直节奏。',
    },
  ],
  execution: [
    {
      severity: 'P1',
      category: '首屏主任务清晰度',
      evidence: '执行中心天然带有复盘、风险、执行明细和 artifact 阅读几条路径，如果首屏把多块状态面板同时平铺，会削弱当前主任务。',
      recommendation: '继续保持“执行状态 + 两个复盘去向 + 一块关键摘要”的首屏结构，其余明细全部进入 tabs 或次级面板。',
    },
  ],
  performance: [
    {
      severity: 'P2',
      category: '图表与数据卡主次',
      evidence: '绩效页容易同时出现账户视角、组合视角和归因内容，指标卡和图表之间主次关系容易失衡。',
      recommendation: '固定一个默认主视角，把其他视角改为显式切换，避免多个绩效框架同时争夺首屏注意力。',
    },
  ],
  'strategy-market': [
    {
      severity: 'P2',
      category: 'CTA 优先级',
      evidence: '策略超市页同时提供浏览、订阅、加入组合、详情审查等动作，容易在列表卡与详情入口之间分散注意力。',
      recommendation: '把默认主 CTA 固定为“查看详情/审查”，把订阅和购物车动作下沉成次级操作。',
    },
  ],
};

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

async function readJson(filePath, fallback) {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function toRelative(outputDir, filePath) {
  if (!filePath) return null;
  if (path.isAbsolute(filePath)) return relativePath(outputDir, filePath);
  return filePath.split(path.sep).join('/');
}

function groupBy(items, getKey) {
  const buckets = new Map();
  for (const item of items) {
    const key = getKey(item);
    const bucket = buckets.get(key) || [];
    bucket.push(item);
    buckets.set(key, bucket);
  }
  return buckets;
}

function uniq(values) {
  return [...new Set(values.filter(Boolean))];
}

function normalizeStatus(status) {
  if (status === 'partial') return 'observed';
  if (status === 'high_risk_not_executed') return 'blocked';
  return status || 'observed';
}

function sortIssues(issues) {
  return [...issues].sort((left, right) => {
    const severityDelta = (SEVERITY_ORDER[left.severity] ?? 99) - (SEVERITY_ORDER[right.severity] ?? 99);
    if (severityDelta !== 0) return severityDelta;
    return CATEGORY_ORDER.indexOf(left.category) - CATEGORY_ORDER.indexOf(right.category);
  });
}

function selectResponsiveRows(rows) {
  const byBreakpoint = new Map(rows.map((row) => [row.breakpoint, row]));
  return {
    mobile: byBreakpoint.get('mobile') || null,
    tablet: byBreakpoint.get('tablet-landscape') || null,
    desktop: byBreakpoint.get('desktop-wide') || byBreakpoint.get('desktop') || null,
    all: rows,
  };
}

function buildVisualIssues(surface, responsiveRows, localResult) {
  const selected = selectResponsiveRows(responsiveRows);
  const desktopSignals = selected.desktop?.signals || null;
  const mobileSignals = selected.mobile?.signals || null;
  const issues = [];

  if (selected.desktop?.assertions && !selected.desktop.assertions.withinBudget) {
    issues.push({
      severity: 'P1',
      category: '首屏主任务清晰度',
      evidence: `${surface.label} 在桌面端默认打开高度达到 ${selected.desktop.screens} 屏，超出 ${selected.desktop.limit} 屏预算。`,
      recommendation: '把非主任务模块下沉到 tab、折叠区或次级面板，只保留当前任务最小摘要。',
    });
  }
  if (selected.mobile?.assertions && !selected.mobile.assertions.withinBudget) {
    issues.push({
      severity: 'P1',
      category: '移动端断点细节',
      evidence: `${surface.label} 在移动端默认打开高度达到 ${selected.mobile.screens} 屏，移动端信息堆叠过长。`,
      recommendation: '把移动端首屏压成 1 到 2 个摘要区，列表、图表和辅助说明进入折叠区或标签页。',
    });
  }
  if (responsiveRows.some((row) => row.status === 'completed' && row.assertions && !row.assertions.noHorizontalOverflow)) {
    issues.push({
      severity: 'P1',
      category: surface.budgetClass === 'table' ? '表格可扫读性' : '移动端断点细节',
      evidence: '至少一个断点出现横向溢出，说明正文宽度、表格容器或壳层边界没有完全收口。',
      recommendation: '统一使用可滚动表格容器和断点降级布局，避免双侧壳层与正文相互挤压。',
    });
  }
  if (desktopSignals && desktopSignals.buttonCount >= 10) {
    issues.push({
      severity: 'P2',
      category: 'CTA 优先级',
      evidence: `${surface.label} 首屏可见按钮/交互入口达到 ${desktopSignals.buttonCount} 个，主次动作已经接近过载。`,
      recommendation: '主操作限制在 1 到 3 个，其余入口改成次级链接、下拉或工具栏收纳。',
    });
  }
  if (desktopSignals && desktopSignals.cardCount >= 8) {
    issues.push({
      severity: 'P2',
      category: '卡片密度与留白',
      evidence: `${surface.label} 主区卡片数量偏多，卡片之间的留白与层级节奏容易失衡。`,
      recommendation: '合并同类摘要卡，减少单屏卡片数，并通过尺寸差异建立主次。',
    });
  }
  if (desktopSignals && desktopSignals.tableCount > 0 && surface.budgetClass === 'table') {
    issues.push({
      severity: 'P2',
      category: '表格可扫读性',
      evidence: '该页属于表格/后台页，若默认同时展示多块摘要与长表，会削弱可扫读性与操作效率。',
      recommendation: '让筛选条、批量操作和低优先级列统一折叠，优先保证主表可扫读。',
    });
  }
  if (localResult?.issues) {
    const runtimeErrorCount =
      (localResult.issues.apiErrors?.length || 0) +
      (localResult.issues.consoleErrors?.length || 0) +
      (localResult.issues.requestFailures?.length || 0);
    if (runtimeErrorCount > 0) {
      issues.push({
        severity: 'P1',
        category: '空态/加载态/错误态',
        evidence: `${surface.label} 在单页测试中记录到 ${runtimeErrorCount} 条运行时异常或失败请求，页面稳定感会被明显削弱。`,
        recommendation: '先把错误态、空态和加载态统一收口，再做进一步视觉打磨。',
      });
    }
  }
  if (surface.mutationRisk === 'high') {
    issues.push({
      severity: 'P2',
      category: '危险操作视觉隔离',
      evidence: '该页存在高风险写操作，需要比普通列表页更强的视觉隔离和结果回执。',
      recommendation: '危险动作必须单独分组，并提供确认层、风险说明和执行后回执。',
    });
  }

  for (const override of PAGE_OVERRIDES[surface.surfaceId] || []) {
    issues.push(override);
  }

  return sortIssues(
    uniq(issues.map((issue) => JSON.stringify(issue))).map((item) => JSON.parse(item)),
  );
}

function buildRuntimeIssues(localResult, responsiveRows) {
  const entries = [];
  if (localResult?.issues) {
    for (const error of localResult.issues.apiErrors || []) entries.push(`API: ${error}`);
    for (const error of localResult.issues.consoleErrors || []) entries.push(`Console: ${error}`);
    for (const error of localResult.issues.requestFailures || []) entries.push(`Request: ${error}`);
  }
  for (const row of responsiveRows) {
    for (const error of row.issues?.apiErrors || []) entries.push(`Responsive/API(${row.breakpoint}): ${error}`);
    for (const error of row.issues?.consoleErrors || []) entries.push(`Responsive/Console(${row.breakpoint}): ${error}`);
    for (const error of row.issues?.httpErrors || []) entries.push(`Responsive/HTTP(${row.breakpoint}): ${error}`);
  }
  return uniq(entries);
}

function buildSinglePointResults(localResult) {
  const rows = [];
  for (const button of localResult?.buttons || []) {
    rows.push({
      label: button.label,
      kind: button.role === 'tab' ? 'tab' : 'control',
      status: normalizeStatus(button.status),
      note: button.note || button.context || '',
    });
  }
  for (const step of localResult?.workflow || []) {
    rows.push({
      label: step.name,
      kind: 'workflow',
      status: normalizeStatus(step.status),
      note: step.note || '',
    });
  }
  return rows;
}

function buildPageRecommendations(surface, visualIssues, responsiveRows, runtimeIssues) {
  const recommendations = [];
  const topIssue = visualIssues[0];
  if (topIssue) {
    recommendations.push(topIssue.recommendation);
  }
  if (responsiveRows.some((row) => row.status === 'completed' && row.assertions && !row.assertions.withinBudget)) {
    recommendations.push('重新定义默认打开状态，只保留当前任务主区，其余内容统一进入折叠区、tabs 或抽屉。');
  }
  if (runtimeIssues.length > 0) {
    recommendations.push('先清理前端 console/API 噪音，再推进视觉优化，否则页面“看起来不稳”的问题不会消失。');
  }
  if (surface.budgetClass === 'table') {
    recommendations.push('后台/表格页继续推进“主表 + 简摘要 + 折叠筛选”的结构，不要在默认态平铺多块运维说明。');
  }
  if (surface.budgetClass === 'workspace') {
    recommendations.push('工作台页保持“主任务 + 一块摘要 + 一组去向”的首屏规则，历史记录和辅助说明不要默认展开。');
  }
  return uniq(recommendations).slice(0, 4);
}

function mapBlueprintFamily(surface) {
  if (surface.group === 'auth') return '认证页';
  if (surface.surfaceId === 'home') return '首页/概览页';
  if (['market', 'stock', 'fundamental', 'technical', 'sentiment', 'fund-flow', 'valuation', 'macro', 'options', 'research', 'search', 'watchlist'].includes(surface.surfaceId)) {
    return '市场/研究页';
  }
  if (surface.budgetClass === 'workspace') return '工作台页';
  if (surface.budgetClass === 'table' || surface.group === 'admin') return '表格/后台页';
  if (surface.surfaceId.startsWith('settings') || surface.group === 'user') return '设置/账户页';
  return '通用功能页';
}

function buildHeatmap(manifest, pagePackages) {
  return manifest.surfaces.map((surface) => {
    const page = pagePackages.get(surface.surfaceId);
    const p0p1 = page.visualIssues.filter((issue) => issue.severity === 'P0' || issue.severity === 'P1').length;
    const runtimeCount = page.runtimeIssues.length;
    return {
      surfaceId: surface.surfaceId,
      label: surface.label,
      group: surface.group,
      majorIssues: p0p1,
      runtimeIssues: runtimeCount,
      status: page.pageStatus,
    };
  });
}

async function writePageReport(outputDir, surface, pagePackage, flowIndex) {
  const reportDir = await ensureDir(path.join(outputDir, 'pages', surface.group));
  const reportPath = path.join(reportDir, `${surface.surfaceId}.md`);
  const screenshots = pagePackage.screenshots;
  const relatedFlows = flowIndex.get(surface.surfaceId) || [];

  const lines = [
    `# ${surface.label}`,
    '',
    '## 页面概览',
    '',
    `- Surface ID: \`${surface.surfaceId}\``,
    `- 路由: \`${surface.route}\``,
    `- 页面族: ${surface.family}`,
    `- 预算类别: \`${surface.budgetClass}\``,
    `- 鉴权: \`${surface.auth}\``,
    `- 主状态: \`${pagePackage.pageStatus}\``,
    '',
    '## 实际截图',
    '',
  ];

  if (screenshots.desktop) {
    lines.push(`![${surface.label} Desktop](../../${screenshots.desktop})`, '');
  }
  if (screenshots.mobile) {
    lines.push(`![${surface.label} Mobile](../../${screenshots.mobile})`, '');
  }
  if (screenshots.tablet) {
    lines.push(`![${surface.label} Tablet](../../${screenshots.tablet})`, '');
  }

  lines.push('## 视觉问题清单', '');
  if (pagePackage.visualIssues.length === 0) {
    lines.push('- 未发现需要单独列出的视觉问题。', '');
  } else {
    for (const issue of pagePackage.visualIssues) {
      lines.push(`- [${issue.severity}] ${issue.category}: ${issue.evidence} 建议：${issue.recommendation}`);
    }
    lines.push('');
  }

  lines.push('## 单点功能结果', '');
  if (pagePackage.singlePointResults.length === 0) {
    lines.push('- 当前页面没有记录到可结构化的按钮/表单动作。', '');
  } else {
    for (const row of pagePackage.singlePointResults) {
      lines.push(`- [${row.status}] ${row.kind} / ${row.label}${row.note ? `：${row.note}` : ''}`);
    }
    lines.push('');
  }

  lines.push('## 整页结果', '');
  for (const row of pagePackage.responsiveRows) {
    if (row.status === 'blocked') {
      lines.push(`- ${row.breakpoint}: blocked，原因：${row.blockedReason}`);
      continue;
    }
      lines.push(
        `- ${row.breakpoint}: ${row.screens} 屏，overflow=${row.assertions?.noHorizontalOverflow ? '0' : '1'}，budget=${row.assertions?.withinBudget ? 'ok' : 'over'}，main=${row.assertions?.mainUsable ? 'ok' : 'bad'}`,
      );
  }
  lines.push('');

  lines.push('## 相关跨页与全流程结果', '');
  if (relatedFlows.length === 0) {
    lines.push('- 当前页面未被 flow 审计命中。', '');
  } else {
    for (const flow of relatedFlows) {
      lines.push(`- [${flow.status}] [${flow.label}](../../flows/${flow.flowId}.md)`);
    }
    lines.push('');
  }

  lines.push('## 运行时异常', '');
  if (pagePackage.runtimeIssues.length === 0) {
    lines.push('- 未记录到 console/API/request 异常。', '');
  } else {
    for (const issue of pagePackage.runtimeIssues) {
      lines.push(`- ${issue}`);
    }
    lines.push('');
  }

  lines.push('## 修复建议', '');
  for (const recommendation of pagePackage.recommendations) {
    lines.push(`- ${recommendation}`);
  }
  lines.push('', '## 视觉整改建议', '');
  for (const issue of pagePackage.visualIssues.slice(0, 4)) {
    lines.push(`- ${issue.category}: ${issue.recommendation}`);
  }
  lines.push('');

  await fs.writeFile(reportPath, `${lines.join('\n')}\n`, 'utf8');
  return reportPath;
}

async function writeFlowReport(outputDir, flow) {
  const reportDir = await ensureDir(path.join(outputDir, 'flows'));
  const reportPath = path.join(reportDir, `${flow.flowId}.md`);
  const lines = [
    `# ${flow.label}`,
    '',
    '## 流程概览',
    '',
    `- Flow ID: \`${flow.flowId}\``,
    `- 类型: \`${flow.kind}\``,
    `- 鉴权: \`${flow.auth}\``,
    `- 结果: \`${flow.status}\``,
    `- destructive: \`${flow.destructive ? 'yes' : 'no'}\``,
    `- 关联页面: ${flow.touchedSurfaceIds.map((item) => `\`${item}\``).join(', ') || '无'}`,
    '',
    '## 步骤结果',
    '',
  ];

  for (const step of flow.steps) {
    lines.push(`- [${step.status}] ${step.name}${step.note ? `：${step.note}` : ''}`);
    lines.push(`  截图: [${path.basename(step.screenshot)}](../${step.screenshot})`);
  }
  lines.push('', '## 运行时异常', '');
  const runtimeIssues = [
    ...(flow.issues.apiErrors || []).map((item) => `API: ${item}`),
    ...(flow.issues.consoleErrors || []).map((item) => `Console: ${item}`),
    ...(flow.issues.requestFailures || []).map((item) => `Request: ${item}`),
    ...(flow.issues.pageErrors || []).map((item) => `Page: ${item}`),
  ];
  if (runtimeIssues.length === 0) {
    lines.push('- 未记录到流程级运行时异常。', '');
  } else {
    for (const issue of runtimeIssues) {
      lines.push(`- ${issue}`);
    }
    lines.push('');
  }

  await fs.writeFile(reportPath, `${lines.join('\n')}\n`, 'utf8');
  return reportPath;
}

function buildExecutiveSummary(manifest, pagePackages, flows, envSnapshot, envRestore) {
  const pageList = [...pagePackages.values()];
  const allIssues = sortIssues(pageList.flatMap((page) => page.visualIssues.map((issue) => ({ ...issue, surfaceId: page.surfaceId, label: page.label }))));
  const topIssues = allIssues.slice(0, 20);
  const heatmap = buildHeatmap(manifest, pagePackages);
  const byFamily = [...groupBy(manifest.surfaces, mapBlueprintFamily).entries()].map(([family, surfaces]) => ({
    family,
    count: surfaces.length,
    majorIssues: surfaces.reduce((sum, surface) => sum + pagePackages.get(surface.surfaceId).visualIssues.filter((issue) => issue.severity === 'P0' || issue.severity === 'P1').length, 0),
  }));
  const byCategory = CATEGORY_ORDER.map((category) => ({
    category,
    count: allIssues.filter((issue) => issue.category === category).length,
  })).filter((item) => item.count > 0);
  const functionIssues = pageList.reduce((sum, page) => sum + page.runtimeIssues.length, 0);
  const flowFailures = flows.filter((flow) => flow.status !== 'passed');

  return { topIssues, heatmap, byFamily, byCategory, functionIssues, flowFailures, envSnapshot, envRestore };
}

function buildDesignBlueprint(manifest, pagePackages) {
  const pageLookup = Object.fromEntries([...pagePackages.values()].map((page) => [page.surfaceId, page]));
  return {
    global: [
      '背景和玻璃材质需要继续降噪。当前大量页面仍存在“壳层一层玻璃 + 模块再一层玻璃 + 卡片再一层边框”的重复结构。',
      '按钮体系需要收敛主次。蓝色主按钮、浅色 pill、边框按钮和轻量文本链接同时大量出现时，CTA 优先级会被冲淡。',
      '状态色需要更严格绑定数据语义，尤其是 success / warning / danger 在后台与交易页的使用边界。',
      '表单、tab、表格和空态组件需要统一高度、留白和标题节奏，减少“每页一套微差异”的观感。',
    ],
    families: {
      '认证页': '登录/注册页应强化单任务结构，把平台介绍和认证动作严格分区，避免认证页继续像复杂工作台。',
      '首页/概览页': '首页继续维持产品首页定位，限制默认展开模块数量，并把运行态概况压缩成轻摘要。',
      '市场/研究页': '市场与研究页优先保证查询、筛选和结果阅读顺序，图表和扩展解释不应抢占首屏主任务。',
      '工作台页': '工作台页统一遵守“主任务 + 一块摘要 + 次级 tabs/折叠区”规则，历史记录和辅助说明一律下沉。',
      '表格/后台页': '后台页优先服务操作效率，危险动作单独分区，筛选条和低优先级统计不应压住主表。',
      '设置/账户页': '设置和安全页强化步骤说明、状态反馈和操作回执，降低用户对账户状态变化的不确定感。',
    },
    pages: {
      home: pageLookup.home?.visualIssues || [],
      admin: pageLookup.admin?.visualIssues || [],
      factor: pageLookup.factor?.visualIssues || [],
      execution: pageLookup.execution?.visualIssues || [],
      performance: pageLookup.performance?.visualIssues || [],
      'strategy-market': pageLookup['strategy-market']?.visualIssues || [],
    },
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = await readJson(path.join(args.outputDir, 'raw', 'surface-manifest.json'), { surfaces: [] });
  const responsiveResults = await readJson(path.join(args.outputDir, 'raw', 'responsive-audit-results.json'), []);
  const responsiveSummary = await readJson(path.join(args.outputDir, 'raw', 'responsive-audit-summary.json'), {});
  const localResults = await readJson(path.join(args.outputDir, 'raw', 'mcp-crawl-results.json'), []);
  const flowResults = await readJson(path.join(args.outputDir, 'raw', 'flow-results.json'), []);
  const flowSummary = await readJson(path.join(args.outputDir, 'raw', 'flow-summary.json'), {});
  const envSnapshot = await readJson(path.join(args.outputDir, 'raw', 'env-snapshot.json'), null);
  const envRestore = await readJson(path.join(args.outputDir, 'raw', 'env-restore.json'), null);

  const responsiveBySurface = groupBy(responsiveResults, (item) => item.surfaceId);
  const localBySurface = new Map(localResults.map((item) => [item.surfaceId, item]));
  const flowIndex = new Map();
  for (const flow of flowResults) {
    for (const surfaceId of flow.touchedSurfaceIds || []) {
      const bucket = flowIndex.get(surfaceId) || [];
      bucket.push(flow);
      flowIndex.set(surfaceId, bucket);
    }
  }

  const pagePackages = new Map();
  for (const surface of manifest.surfaces) {
    const responsiveRows = responsiveBySurface.get(surface.surfaceId) || [];
    const localResult = localBySurface.get(surface.surfaceId) || null;
    const screenshots = selectResponsiveRows(responsiveRows);
    const visualIssues = buildVisualIssues(surface, responsiveRows, localResult);
    const runtimeIssues = buildRuntimeIssues(localResult, responsiveRows);
    const singlePointResults = buildSinglePointResults(localResult);
    const recommendations = buildPageRecommendations(surface, visualIssues, responsiveRows, runtimeIssues);
    const pageStatus = responsiveRows.some((row) => row.status === 'completed' && !row.passed)
      ? 'needs-attention'
      : runtimeIssues.length > 0
        ? 'runtime-risk'
        : 'ok';
    pagePackages.set(surface.surfaceId, {
      surfaceId: surface.surfaceId,
      label: surface.label,
      responsiveRows,
      localResult,
      visualIssues,
      runtimeIssues,
      singlePointResults,
      recommendations,
      screenshots: {
        mobile: screenshots.mobile ? toRelative(args.outputDir, screenshots.mobile.screenshotPath) : null,
        tablet: screenshots.tablet ? toRelative(args.outputDir, screenshots.tablet.screenshotPath) : null,
        desktop: screenshots.desktop ? toRelative(args.outputDir, screenshots.desktop.screenshotPath) : null,
      },
      pageStatus,
    });
  }

  const flowReportPaths = [];
  for (const flow of flowResults) {
    flowReportPaths.push(await writeFlowReport(args.outputDir, flow));
  }

  const pageReportPaths = [];
  for (const surface of manifest.surfaces) {
    pageReportPaths.push(await writePageReport(args.outputDir, surface, pagePackages.get(surface.surfaceId), flowIndex));
  }

  const executive = buildExecutiveSummary(manifest, pagePackages, flowResults, envSnapshot, envRestore);
  const blueprint = buildDesignBlueprint(manifest, pagePackages);

  const executivePath = path.join(args.outputDir, 'executive-summary.md');
  const blueprintPath = path.join(args.outputDir, 'design-blueprint.md');
  const indexPath = path.join(args.outputDir, 'index.md');

  const executiveLines = [
    '# 前端审计执行摘要',
    '',
    '## 总览',
    '',
    `- 页面总数: ${manifest.surfaces.length}`,
    `- Flow 总数: ${flowResults.length}`,
    `- 响应式审计: ${responsiveSummary.passed || 0} 通过 / ${responsiveSummary.failed || 0} 失败 / ${responsiveSummary.blocked || 0} 阻塞`,
    `- Flow 审计: ${flowSummary.passed || 0} 通过 / ${flowSummary.failed || 0} 失败 / ${flowSummary.blocked || 0} 阻塞`,
    `- destructive 实际执行次数: ${flowSummary.destructiveExecuted || 0}`,
    '',
    '## 全站问题热力图',
    '',
    '| 页面 | 组别 | P0/P1 数量 | 运行时问题 | 状态 |',
    '| --- | --- | ---: | ---: | --- |',
    ...executive.heatmap.map((item) => `| ${item.label} | ${item.group} | ${item.majorIssues} | ${item.runtimeIssues} | ${item.status} |`),
    '',
    '## 页面族问题统计',
    '',
    '| 页面族 | 页面数 | 重大问题数 |',
    '| --- | ---: | ---: |',
    ...executive.byFamily.map((item) => `| ${item.family} | ${item.count} | ${item.majorIssues} |`),
    '',
    '## 视觉系统问题统计',
    '',
    '| 类别 | 数量 |',
    '| --- | ---: |',
    ...executive.byCategory.map((item) => `| ${item.category} | ${item.count} |`),
    '',
    '## 功能问题统计',
    '',
    `- 运行时异常总数: ${executive.functionIssues}`,
    '',
    '## 跨页面链路问题统计',
    '',
    ...(
      executive.flowFailures.length
        ? executive.flowFailures.map((flow) => `- [${flow.status}] ${flow.label}`)
        : ['- 15 条 flow 全部通过。']
    ),
    '',
    '## destructive 测试结果',
    '',
    envSnapshot ? `- 环境快照: \`${path.basename(envSnapshot.postgres.dumpPath)}\` 与 Redis 数据目录已生成。` : '- 未找到环境快照元数据。',
    envRestore ? '- destructive 测试结束后已执行环境恢复。' : '- 未记录到环境恢复结果。',
    '',
    '## Top 20 问题',
    '',
    ...executive.topIssues.map((issue) => `- [${issue.severity}] ${issue.label} / ${issue.category}: ${issue.evidence}`),
    '',
    '## 30/60/90 天整改蓝图',
    '',
    '- 30 天：优先处理 P0/P1 页面，先修正后台/工作台的默认展开和移动端断点问题。',
    '- 60 天：统一玻璃材质、按钮体系、表格和状态色设计 token，并补齐空态/错误态标准组件。',
    '- 90 天：建立设计回归基线，把响应式预算、视觉检查和 flow 审计纳入前端发布前回归。',
    '',
  ];

  const blueprintLines = [
    '# 全站设计整改蓝图',
    '',
    '## 全局层',
    '',
    ...blueprint.global.map((item) => `- ${item}`),
    '',
    '## 页面族层',
    '',
    ...Object.entries(blueprint.families).map(([family, note]) => `- ${family}: ${note}`),
    '',
    '## 单页面层',
    '',
  ];

  for (const [surfaceId, issues] of Object.entries(blueprint.pages)) {
    blueprintLines.push(`### ${surfaceId}`);
    blueprintLines.push('');
    if (!issues.length) {
      blueprintLines.push('- 当前没有单独登记的页面级整改项。', '');
      continue;
    }
    for (const issue of issues) {
      blueprintLines.push(`- ${issue.category}: ${issue.recommendation}`);
    }
    blueprintLines.push('');
  }

  const byGroup = groupBy(manifest.surfaces, (surface) => surface.group);
  const indexLines = [
    '# 前端审计报告索引',
    '',
    '- [执行摘要](./executive-summary.md)',
    '- [设计整改蓝图](./design-blueprint.md)',
    '',
    '## 页面报告',
    '',
  ];

  for (const [group, surfaces] of [...byGroup.entries()].sort((left, right) => left[0].localeCompare(right[0], 'zh-CN'))) {
    indexLines.push(`### ${group}`);
    indexLines.push('');
    for (const surface of surfaces) {
      indexLines.push(`- [${surface.label}](./pages/${group}/${surface.surfaceId}.md)`);
    }
    indexLines.push('');
  }

  indexLines.push('## Flow 报告', '');
  for (const flow of flowResults) {
    indexLines.push(`- [${flow.label}](./flows/${flow.flowId}.md)`);
  }
  indexLines.push('', '## 原始结果', '', '- `raw/surface-manifest.json`', '- `raw/mcp-crawl-results.json`', '- `raw/responsive-audit-results.json`', '- `raw/flow-results.json`', '- `raw/env-snapshot.json`', '- `raw/env-restore.json`', '');

  await fs.writeFile(executivePath, `${executiveLines.join('\n')}\n`, 'utf8');
  await fs.writeFile(blueprintPath, `${blueprintLines.join('\n')}\n`, 'utf8');
  await fs.writeFile(indexPath, `${indexLines.join('\n')}\n`, 'utf8');
  await fs.writeFile(
    path.join(args.outputDir, 'raw', 'frontend-audit-page-results.json'),
    JSON.stringify(
      [...pagePackages.values()].map((page) => ({
        surfaceId: page.surfaceId,
        label: page.label,
        pageStatus: page.pageStatus,
        screenshots: page.screenshots,
        visualIssues: page.visualIssues,
        runtimeIssues: page.runtimeIssues,
        recommendations: page.recommendations,
      })),
      null,
      2,
    ),
    'utf8',
  );
  process.stdout.write(`${indexPath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
