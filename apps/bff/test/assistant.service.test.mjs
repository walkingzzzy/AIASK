import test from 'node:test';
import assert from 'node:assert/strict';

const { AssistantService } = await import('../dist/assistant/assistant.service.js');

const cacheStub = {
  getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
  resolveTtl: () => 60,
  set: async () => {},
};

test('AssistantService.analyzeWorkflow degrades gracefully when MCP returns a failed workflow payload', async () => {
  const service = new AssistantService(
    {
      callTool: async (tool) => {
        assert.equal(tool, 'analyze_stock_workflow');
        return { success: false, message: 'workflow offline' };
      },
    },
    cacheStub,
  );

  const response = await service.analyzeWorkflow('600519');
  assert.equal(response.card?.action, 'watch');
  assert.match(response.card?.summary ?? '', /AI 诊断暂时没有拿到完整结论/);
  assert.equal(response.raw?.data?.availability_status, 'unavailable');
  assert.equal(response.result_contract?.status, 'unavailable');
  assert.equal(response.result_contract?.recommendedActions?.[0]?.actionId, 'global.open-stock-detail');
});

test('AssistantService.analyzeWorkflow degrades gracefully when MCP transport times out', async () => {
  const service = new AssistantService(
    {
      callTool: async (tool) => {
        assert.equal(tool, 'analyze_stock_workflow');
        throw new Error('MCP error -32001: Request timed out');
      },
    },
    cacheStub,
  );

  const response = await service.analyzeWorkflow('600519');
  assert.equal(response.card?.action, 'watch');
  assert.match(response.card?.summary ?? '', /AI 诊断暂时没有拿到完整结论/);
  assert.equal(response.raw?.data?.availability_status, 'unavailable');
  assert.match(response.result_contract?.platformMeta?.fallbackReason?.join(' / ') ?? '', /响应较慢/);
});

test('AssistantService.shouldBuy emits additive result_contract for unified result workbench', async () => {
  const service = new AssistantService(
    {
      callTool: async (tool) => {
        assert.equal(tool, 'should_i_buy');
        return {
          meta: { fetchedAt: '2026-04-21T09:30:00.000Z' },
          data: {
            action: 'buy',
            confidence: 0.82,
            summary: '盈利改善，估值仍可接受。',
            reasons: ['盈利改善', '行业景气回升'],
            risks: ['短期波动'],
          },
        };
      },
    },
    cacheStub,
  );

  const response = await service.shouldBuy('600519');
  assert.equal(response.result_contract?.platformMeta?.sourceTool, 'should_i_buy');
  assert.equal(response.result_contract?.workbenchTask?.kind, 'assistant-result');
  assert.equal(response.result_contract?.skillSuggestions?.length, 3);
  assert.equal(response.result_contract?.recommendedActions?.[0]?.actionId, 'global.open-stock-detail');
  assert.equal(response.result_contract?.recommendedActions?.[0]?.payload?.code, '600519');
  assert.equal(response.result_contract?.recommendedActions?.[1]?.actionId, 'assistant.open-copilot-followup');
  assert.match(
    response.result_contract?.recommendedLinks?.map((item) => item.label).join(' / ') ?? '',
    /去工厂运行态/,
  );
  assert.match(response.result_contract?.summary ?? '', /盈利改善/);
});

test('AssistantService.getIndustryChain marks mismatched keyword results as degraded', async () => {
  const service = new AssistantService(
    {
      callTool: async (tool, args) => {
        assert.equal(tool, 'get_industry_chain');
        assert.equal(args.keyword, '银行金融科技');
        return {
          data: {
            chains: [
              {
                id: 'new-energy',
                name: '新能源产业链',
                upstream: ['锂矿'],
                midstream: ['电池'],
                downstream: ['整车'],
              },
            ],
          },
        };
      },
    },
    cacheStub,
  );

  const response = await service.getIndustryChain('银行金融科技');
  assert.equal(response.result_contract?.platformMeta?.degraded, true);
  assert.equal(response.result_contract?.platformMeta?.requested_keyword, '银行金融科技');
  assert.equal(response.result_contract?.platformMeta?.matched_keyword, '新能源产业链');
  assert.match(response.result_contract?.summary ?? '', /不匹配/);
});
