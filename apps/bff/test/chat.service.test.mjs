import test from 'node:test';
import assert from 'node:assert/strict';

const { ChatService } = await import('../dist/chat/chat.service.js');
const { createChatToolTrace } = await import('../dist/chat/tool-trace.js');

function createChatService() {
  return new ChatService(
    {},
    {},
    {},
    {},
    {},
    {},
    {},
    {},
  );
}

function createFrontendContext(pageKey = 'market', stockCode = '000988') {
  const routes = [
    {
      pageKey: 'market',
      path: '/market',
      module: 'market',
      title: '行情看板',
      summary: '行情看板',
      aliases: ['行情', '看盘'],
      stockAware: true,
    },
    {
      pageKey: 'fundamental',
      path: '/fundamental',
      module: 'research',
      title: '基本面',
      summary: '基本面验证',
      aliases: ['基本面', '财务'],
      stockAware: true,
    },
    {
      pageKey: 'paper-trading',
      path: '/paper-trading',
      module: 'trade',
      title: '模拟交易',
      summary: '模拟交易',
      aliases: ['模拟交易', '下单'],
      stockAware: true,
    },
    {
      pageKey: 'research',
      path: '/research',
      module: 'research',
      title: '研报公告',
      summary: '研究验证',
      aliases: ['研究', '研报'],
      stockAware: true,
    },
  ];
  const currentRoute = routes.find((route) => route.pageKey === pageKey) ?? routes[0];
  return {
    generatedAt: Date.now(),
    route: `${currentRoute.path}${stockCode ? `?code=${stockCode}` : ''}`,
    appMap: {
      modules: [{ module: 'market', title: '看盘', pageKeys: ['market'] }],
      routes,
    },
    currentRoute: {
      ...currentRoute,
      primaryGoal: '测试目标',
      capabilities: ['测试能力'],
      relatedPageKeys: ['fundamental', 'paper-trading', 'research'],
    },
    relatedRoutes: routes.filter((route) => route.pageKey !== currentRoute.pageKey).map((route) => ({
      ...route,
      primaryGoal: '测试目标',
    })),
    taskFlow: {
      id: 'stock-research-flow',
      title: '个股研究链路',
      summary: '看盘到研究再交易',
      currentStepIndex: pageKey === 'market' ? 0 : pageKey === 'fundamental' ? 1 : 0,
      steps: [
        { pageKey: 'market', title: '看盘锁定标的', goal: '确认行情', nextPageKey: 'fundamental' },
        { pageKey: 'fundamental', title: '基本面验证', goal: '验证财务', nextPageKey: 'paper-trading' },
        { pageKey: 'paper-trading', title: '模拟交易验证', goal: '模拟交易' },
      ],
    },
    workspaceContext: { stockCode },
  };
}

test('ChatService builds a visible final fallback from page context when the model returns no content', () => {
  const service = createChatService();
  const trace = createChatToolTrace({
    mode: 'copilot',
    pageKey: 'home',
    stockCode: '601398',
  });

  const fallback = service.buildToolOnlyFallbackAnswer(trace, {
    pageKey: 'home',
    title: '首页',
    summary: '当前监控 4 个指数，3 条市场异常，活跃告警 6 条。',
    selectedCode: '601398',
    evidenceSummary: ['指数监控正常', '市场异常 3 条'],
    riskNotes: ['活跃告警较多', '资金流需要复核'],
    dataFreshness: '实时',
  });

  assert.match(fallback, /基于页面上下文生成/);
  assert.match(fallback, /当前监控 4 个指数/);
  assert.match(fallback, /风险关注/);
  assert.match(fallback, /活跃告警较多/);
});

test('ChatService does not fabricate fallback content without page evidence or tool results', () => {
  const service = createChatService();
  const trace = createChatToolTrace({ mode: 'chat' });

  const fallback = service.buildToolOnlyFallbackAnswer(trace, null);

  assert.equal(fallback, '');
});

test('ChatService keeps advisory Copilot action requests pending', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'assistant.run-unified-decision',
      label: '运行统一决策',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '下一步最合适的 AI 操作是什么？' }],
    { pageKey: 'assistant', title: 'AI 中心', summary: '测试上下文' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'assistant.run-unified-decision', autoExecute: true },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, false);
  assert.equal(event?.autoExecute, false);
});

test('ChatService auto-executes readonly actions only for explicit execution intent', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'assistant.run-unified-decision',
      label: '运行统一决策',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '请运行统一决策' }],
    { pageKey: 'assistant', title: 'AI 中心', summary: '测试上下文' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'assistant.run-unified-decision' },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitStockDetailIntent, false);
  assert.equal(event?.actionId, 'assistant.run-unified-decision');
  assert.equal(event?.autoExecute, true);
});

test('ChatService auto-executes stock detail opening for explicit realtime quote intent', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '请打开 000988 实时行情页' }],
    { pageKey: 'search', title: '智能搜索', summary: '存在搜索结果' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail', payload: { code: '000988' } },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(event?.autoExecute, true);
});

test('ChatService treats "分析 000988" as explicit stock detail intent when stock opening is available', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '分析 000988' }],
    { pageKey: 'assistant', title: 'AI 中心', summary: '测试上下文' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail', payload: { code: '000988' } },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitStockDetailIntent, true);
  assert.equal(intent.stockDetailCode, '000988');
  assert.equal(event?.actionId, 'global.open-stock-detail');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});

test('ChatService opens the current stock when the user says "打开这支股票"', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '打开这支股票' }],
    { pageKey: 'search', title: '智能搜索', summary: '测试上下文', stockCode: '000988' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail' },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitStockDetailIntent, true);
  assert.equal(intent.stockDetailCode, '000988');
  assert.equal(event?.actionId, 'global.open-stock-detail');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});

test('ChatService rewrites mistaken search action to stock detail for explicit stock opening intent', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-search',
      label: '打开智能搜索',
      mutationEffect: 'readonly',
    },
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '查看 000988 实时行情' }],
    { pageKey: 'assistant', title: 'AI 中心', summary: '测试上下文' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-search', payload: { code: '000988' } },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitStockDetailIntent, true);
  assert.equal(event?.actionId, 'global.open-stock-detail');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});

test('ChatService can resolve stock detail rewrite from action payload code', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-search',
      label: '打开智能搜索',
      mutationEffect: 'readonly',
    },
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '查看实时行情' }],
    { pageKey: 'assistant', title: 'AI 中心', summary: '测试上下文' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-search', payload: { code: '000988' } },
    actions,
    intent,
  );

  assert.equal(intent.explicitStockDetailIntent, false);
  assert.equal(event?.actionId, 'global.open-stock-detail');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});

test('ChatService resolves stock detail code from recommended actions and links', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intentFromAction = service.analyzeClientActionIntent(
    [{ role: 'user', content: '分析这支股票' }],
    {
      pageKey: 'search',
      title: '智能搜索',
      summary: '测试上下文',
      recommendedActions: [
        {
          id: 'search.open-stock-detail',
          actionId: 'global.open-stock-detail',
          label: '打开个股详情',
          payload: { code: '000988' },
        },
      ],
    },
    null,
    actions,
  );
  const eventFromAction = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail' },
    actions,
    intentFromAction,
  );

  const intentFromLink = service.analyzeClientActionIntent(
    [{ role: 'user', content: '打开这支股票' }],
    {
      pageKey: 'search',
      title: '智能搜索',
      summary: '测试上下文',
      recommendedLinks: [{ id: 'stock-link', label: '个股详情', href: '/stock?code=600519' }],
    },
    null,
    actions,
  );
  const eventFromLink = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail' },
    actions,
    intentFromLink,
  );

  assert.equal(eventFromAction?.payload?.code, '000988');
  assert.equal(eventFromAction?.autoExecute, true);
  assert.equal(eventFromLink?.payload?.code, '600519');
  assert.equal(eventFromLink?.autoExecute, true);
});

test('ChatService keeps stock detail opening pending for advisory analysis questions', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '下一步怎么分析' }],
    { pageKey: 'search', title: '智能搜索', summary: '测试上下文', stockCode: '000988' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail', payload: { code: '000988' }, autoExecute: true },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, false);
  assert.equal(intent.explicitStockDetailIntent, false);
  assert.equal(event?.autoExecute, false);
});

test('ChatService does not auto-open stock detail for current search summaries', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '总结当前搜索结果' }],
    {
      pageKey: 'search',
      title: '智能搜索',
      summary: '测试上下文',
      stockCode: '000988',
      recommendedActions: [
        {
          id: 'search.open-stock-detail',
          actionId: 'global.open-stock-detail',
          label: '打开个股详情',
          payload: { code: '000988' },
        },
      ],
    },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-stock-detail', autoExecute: true },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, false);
  assert.equal(intent.explicitStockDetailIntent, false);
  assert.equal(event?.autoExecute, false);
});

test('ChatService does not rewrite unrelated open intents on stock-aware pages', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-watchlist',
      label: '打开自选股',
      mutationEffect: 'readonly',
    },
    {
      id: 'global.open-stock-detail',
      label: '打开个股详情',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '打开自选股' }],
    { pageKey: 'stock', title: '个股详情', summary: '测试上下文', stockCode: '000988' },
    null,
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-watchlist' },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitStockDetailIntent, false);
  assert.equal(event?.actionId, 'global.open-watchlist');
  assert.equal(event?.autoExecute, true);
});

test('ChatService keeps personal strategy stateful actions guarded by write intent', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'strategy.persist-personal-update',
      label: '保存个人策略',
      mutationEffect: 'stateful',
      strategyActionKind: 'persist_update',
    },
  ];
  const pageContext = {
    pageKey: 'strategy-detail',
    title: '策略详情',
    summary: '个人策略上下文',
    objectType: 'personal_strategy',
    raw: { personalStrategyContext: { editable: true } },
  };
  const advisoryIntent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '请说明这个策略下一步怎么优化' }],
    pageContext,
    null,
    actions,
  );
  const writeIntent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '请直接保存这次策略优化' }],
    pageContext,
    null,
    actions,
  );

  const advisoryEvent = service.buildClientActionEvent(
    { actionId: 'strategy.persist-personal-update', autoExecute: true },
    actions,
    advisoryIntent,
  );
  const writeEvent = service.buildClientActionEvent(
    { actionId: 'strategy.persist-personal-update' },
    actions,
    writeIntent,
  );

  assert.equal(advisoryIntent.explicitPersonalStrategyWrite, false);
  assert.equal(advisoryEvent?.autoExecute, false);
  assert.equal(writeIntent.explicitPersonalStrategyWrite, true);
  assert.equal(writeEvent?.autoExecute, true);
});

test('ChatService opens registered route for explicit page navigation intent', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-route',
      label: '打开前端页面',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '进入基本面页' }],
    { pageKey: 'market', title: '行情看板', summary: '测试上下文', stockCode: '000988' },
    createFrontendContext('market', '000988'),
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-search' },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitRouteIntent, true);
  assert.equal(intent.routePageKey, 'fundamental');
  assert.equal(event?.actionId, 'global.open-route');
  assert.equal(event?.payload?.pageKey, 'fundamental');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});

test('ChatService carries current stock code when opening paper trading route', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-route',
      label: '打开前端页面',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '打开模拟交易页' }],
    { pageKey: 'fundamental', title: '基本面', summary: '测试上下文' },
    createFrontendContext('fundamental', '000988'),
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-route' },
    actions,
    intent,
  );

  assert.equal(event?.actionId, 'global.open-route');
  assert.equal(event?.payload?.pageKey, 'paper-trading');
  assert.equal(event?.payload?.href, '/paper-trading');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});

test('ChatService keeps advisory next-step analysis from auto navigating', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-route',
      label: '打开前端页面',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '下一步怎么分析' }],
    { pageKey: 'market', title: '行情看板', summary: '测试上下文', stockCode: '000988' },
    createFrontendContext('market', '000988'),
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-route', payload: { pageKey: 'fundamental', code: '000988' }, autoExecute: true },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, false);
  assert.equal(intent.explicitRouteIntent, false);
  assert.equal(event?.autoExecute, false);
});

test('ChatService routes explicit next-step execution through task flow', () => {
  const service = createChatService();
  const actions = [
    {
      id: 'global.open-route',
      label: '打开前端页面',
      mutationEffect: 'readonly',
    },
  ];
  const intent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '带我去下一步' }],
    { pageKey: 'market', title: '行情看板', summary: '测试上下文', stockCode: '000988' },
    createFrontendContext('market', '000988'),
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'global.open-search' },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
  assert.equal(intent.explicitRouteIntent, true);
  assert.equal(event?.actionId, 'global.open-route');
  assert.equal(event?.payload?.pageKey, 'fundamental');
  assert.equal(event?.payload?.code, '000988');
  assert.equal(event?.autoExecute, true);
});
