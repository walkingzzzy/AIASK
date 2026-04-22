import test from 'node:test';
import assert from 'node:assert/strict';

const { CHAT_REASONING_REPLACEMENT, sanitizeReasoningDelta } = await import('../dist/chat/chat-safety.js');
const { buildSystemPrompt } = await import('../dist/chat/tools/system-prompt.js');

test('buildSystemPrompt includes explicit reasoning leak and high-risk request constraints', () => {
  const prompt = buildSystemPrompt({
    kycLevel: 'C3',
    riskLevel: 'medium',
    profileSummary: '偏好中等风险',
    recentEmotions: ['谨慎'],
  });

  assert.match(prompt, /不得暴露内部推理/);
  assert.match(prompt, /不得向用户输出“我需要先/);
  assert.match(prompt, /保证收益、明天涨停、内幕消息、代下单/);
});

test('sanitizeReasoningDelta keeps ordinary assistant output intact', () => {
  const result = sanitizeReasoningDelta('贵州茅台当前估值需要结合盈利增速与现金流一起看。', false);
  assert.equal(result.content, '贵州茅台当前估值需要结合盈利增速与现金流一起看。');
  assert.equal(result.replaced, false);
});

test('sanitizeReasoningDelta replaces XML-style reasoning blocks and only emits the replacement once', () => {
  const first = sanitizeReasoningDelta('<think>先分析用户问题，再决定是否调用工具</think>', false);
  assert.equal(first.content, CHAT_REASONING_REPLACEMENT);
  assert.equal(first.replaced, true);

  const second = sanitizeReasoningDelta('<reasoning>继续展示内部分析</reasoning>', true);
  assert.equal(second.content, '');
  assert.equal(second.replaced, true);
});

test('sanitizeReasoningDelta catches English planning leakage and tool planning leakage', () => {
  const english = sanitizeReasoningDelta('I need to call get_realtime_quote before answering.', false);
  assert.equal(english.content, CHAT_REASONING_REPLACEMENT);
  assert.equal(english.replaced, true);

  const toolLeak = sanitizeReasoningDelta('接下来我会调用工具，并组织参数后再回答。', false);
  assert.equal(toolLeak.content, CHAT_REASONING_REPLACEMENT);
  assert.equal(toolLeak.replaced, true);
});

test('sanitizeReasoningDelta catches Chinese planning leakage', () => {
  const result = sanitizeReasoningDelta('用户问的是当前能不能买入，我需要先分析量价和风险。', false);
  assert.equal(result.content, CHAT_REASONING_REPLACEMENT);
  assert.equal(result.replaced, true);
});
