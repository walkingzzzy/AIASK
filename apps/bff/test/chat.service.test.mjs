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
    actions,
  );

  const event = service.buildClientActionEvent(
    { actionId: 'assistant.run-unified-decision' },
    actions,
    intent,
  );

  assert.equal(intent.explicitActionExecution, true);
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
    actions,
  );
  const writeIntent = service.analyzeClientActionIntent(
    [{ role: 'user', content: '请直接保存这次策略优化' }],
    pageContext,
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
