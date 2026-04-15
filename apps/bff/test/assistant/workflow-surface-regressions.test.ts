import 'reflect-metadata';
import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { AssistantService } from '../../src/assistant/assistant.service';
import { FactorService } from '../../src/factor/factor.service';
import { StrategyMarketService } from '../../src/strategy/strategy.service';
import { DataService } from '../../src/data/data.service';
import { McpGatewayService } from '../../src/mcp-gateway/mcp-gateway.service';

test('assistant analysis workflow exposes normalized decision card', async () => {
  const service = new AssistantService(
    {
      callTool: async (name: string, args: Record<string, unknown>) => {
        assert.equal(name, 'analyze_stock_workflow');
        assert.equal(args.code, '600519');
        return {
          success: true,
          data: {
            steps: [
              {
                step: 'decision_summary',
                output: {
                  success: true,
                  data: {
                    action: 'buy',
                    confidence: 0.74,
                    summary: '多维证据偏多。',
                    reasons: ['基本面改善'],
                    risks: ['短线波动放大'],
                    compliance_notice: '仅供参考',
                  },
                },
              },
            ],
            summary: {
              decision_action: 'buy',
              quote_price: 1688.0,
            },
            artifacts: {
              stock_profile_resource: 'resource://stock/600519/profile',
            },
          },
          meta: {
            source_chain: ['workflow.analyze_stock', 'tool.get_unified_decision_summary'],
          },
        };
      },
    } as never,
    {} as never,
  );

  const result = await service.analyzeWorkflow('600519', { includeDecision: true });

  assert.equal(result.card.action, 'buy');
  assert.equal(result.card.confidence, 0.74);
  assert.equal(result.card.reasons[0], '基本面改善');
  assert.equal(result.card.risks[0], '短线波动放大');
  assert.equal(result.card.dataProvenance[0], 'workflow.analyze_stock');
  assert.match(result.card.summary, /多维证据偏多/);
  assert.match(result.card.executionPlan.join('；'), /resource:\/\/stock\/600519\/profile/);
});

test('factor candidate workflow forwards deduplicated workflow arguments', async () => {
  let capturedName = '';
  let capturedArgs: Record<string, unknown> = {};
  const service = new FactorService(
    {
      callTool: async (name: string, args: Record<string, unknown>) => {
        capturedName = name;
        capturedArgs = args;
        return {
          success: true,
          data: {
            workflow: 'factor_candidate_workflow',
            task: 'pipeline',
            summary: { artifact_id: 'art_factor_001' },
          },
        };
      },
    } as never,
    {} as never,
  );

  const result = await service.candidateWorkflow({
    task: 'pipeline',
    stock_codes: ['600519', '600519', '000001'],
    lookback_bars: 240,
    allow_fallback: false,
    run_scheduler_now: true,
  });

  assert.equal(capturedName, 'factor_candidate_workflow');
  assert.deepEqual(capturedArgs.codes, ['600519', '000001']);
  assert.equal(capturedArgs.lookback_bars, 240);
  assert.equal(capturedArgs.allow_fallback, false);
  assert.equal(capturedArgs.run_scheduler_now, true);
  assert.equal(result.workflow, 'factor_candidate_workflow');
  assert.equal(result.artifact_id, 'art_factor_001');
  assert.equal((result.summary as Record<string, unknown>).artifact_id, 'art_factor_001');
});

test('strategy review workflow uses AI workflow entrypoint', async () => {
  let capturedName = '';
  let capturedArgs: Record<string, unknown> = {};
  const service = new StrategyMarketService(
    {
      callTool: async (name: string, args: Record<string, unknown>) => {
        capturedName = name;
        capturedArgs = args;
        return {
          success: true,
          data: {
            workflow: 'strategy_review_workflow',
            strategy_id: 'strat_demo',
          },
        };
      },
    } as never,
    {} as never,
  );

  const result = await service.reviewWorkflow('strat_demo', { run_factory_once: true });

  assert.equal(capturedName, 'strategy_review_workflow');
  assert.equal(capturedArgs.strategy_id, 'strat_demo');
  assert.equal(capturedArgs.run_factory_once, true);
  assert.equal(result.workflow, 'strategy_review_workflow');
});

test('strategy detail normalization passively preserves incubation overview shells', async () => {
  const service = new StrategyMarketService(
    {
      callTool: async () => ({
        data: {
          strategy: {
            id: 'strat_demo',
            name: 'demo',
          },
          incubation_overview: {
            strategy_id: 'strat_demo',
            prediction_quality_label: 'mixed',
            execution_quality_label: 'insufficient_evidence',
            confidence_contract_status: 'missing',
          },
          incubation_account: {
            account_id: 'paper_demo',
          },
        },
      }),
    } as never,
    {} as never,
  );

  const result = await service.detail('strat_demo') as {
    incubation_overview?: { strategy_id?: string; prediction_quality_label?: string };
    view_model?: {
      incubation?: {
        overview?: { confidence_contract_status?: string };
        account?: { account_id?: string };
      };
    };
  };

  assert.equal(result.incubation_overview?.strategy_id, 'strat_demo');
  assert.equal(result.incubation_overview?.prediction_quality_label, 'mixed');
  assert.equal(result.view_model?.incubation?.overview?.confidence_contract_status, 'missing');
  assert.equal(result.view_model?.incubation?.account?.account_id, 'paper_demo');
});

test('strategy detail normalization preserves pipeline gate diagnostics', async () => {
  const service = new StrategyMarketService(
    {
      callTool: async () => ({
        data: {
          strategy: {
            id: 'strat_demo',
            name: 'demo',
          },
          latest_incubation_pipeline_snapshot: {
            pipeline_stage: 'observe',
            pipeline_status: 'observing',
            readiness_score: 0.42,
            priority_score: 0.42,
            gate_status: 'observe',
            gate_reasons: ['execution_audit_gate:insufficient_samples'],
            hard_gate_result: {
              pipeline_stage: 'observe',
              execution_audit_gate_status: 'insufficient_samples',
              passed: false,
            },
          },
        },
      }),
    } as never,
    {} as never,
  );

  const result = await service.detail('strat_demo') as {
    view_model?: {
      incubation?: {
        latest_pipeline_snapshot?: {
          gate_status?: string;
          gate_reasons?: string[];
          priority_score?: number;
          hard_gate_result?: { execution_audit_gate_status?: string; passed?: boolean };
        };
      };
    };
  };

  assert.equal(result.view_model?.incubation?.latest_pipeline_snapshot?.gate_status, 'observe');
  assert.deepEqual(result.view_model?.incubation?.latest_pipeline_snapshot?.gate_reasons, ['execution_audit_gate:insufficient_samples']);
  assert.equal(result.view_model?.incubation?.latest_pipeline_snapshot?.priority_score, 0.42);
  assert.equal(result.view_model?.incubation?.latest_pipeline_snapshot?.hard_gate_result?.execution_audit_gate_status, 'insufficient_samples');
  assert.equal(result.view_model?.incubation?.latest_pipeline_snapshot?.hard_gate_result?.passed, false);
});

test('strategy capabilities preserve high-confidence feature flags', async () => {
  const service = new StrategyMarketService(
    {
      callTool: async () => ({
        data: {
          high_confidence_enabled: true,
          evidence_contract_enabled: false,
          confidence_diagnostics_enabled: true,
          execution_audit_enabled: false,
          quality_ui_v2_enabled: true,
          high_confidence_feature_flags: {
            high_confidence_enabled: true,
            evidence_contract_enabled: false,
            confidence_diagnostics_enabled: true,
            execution_audit_enabled: false,
            quality_ui_v2_enabled: true,
          },
        },
      }),
    } as never,
    {} as never,
  );

  const result = await service.capabilities() as {
    quality_ui_v2_enabled?: boolean;
    high_confidence_enabled?: boolean;
    high_confidence_feature_flags?: { quality_ui_v2_enabled?: boolean };
  };

  assert.equal(result.high_confidence_enabled, true);
  assert.equal(result.quality_ui_v2_enabled, true);
  assert.equal(result.high_confidence_feature_flags?.quality_ui_v2_enabled, true);
});

test('data service proxies tool catalog and workflow guide resources', async () => {
  const uris: string[] = [];
  const service = new DataService({
    readResource: async (uri: string) => {
      uris.push(uri);
      return { uri, ok: true };
    },
    callTool: async () => ({ success: true }),
  } as never);

  const catalog = await service.getToolCatalog();
  const guide = await service.getWorkflowGuide('stock-analysis-guide');

  assert.equal(catalog.resourceUri, 'resource://server/tool-catalog');
  assert.equal((catalog.result as Record<string, unknown>).ok, true);
  assert.equal(guide.resourceUri, 'resource://workflow/stock-analysis/guide');
  assert.deepEqual(uris, ['resource://server/tool-catalog', 'resource://workflow/stock-analysis/guide']);
});

test('data service proxies lineage and research object resources', async () => {
  const uris: string[] = [];
  const service = new DataService({
    readResource: async (uri: string) => {
      uris.push(uri);
      return { uri, ok: true };
    },
    callTool: async () => ({ success: true }),
  } as never);

  const run = await service.getRunSnapshot('run_demo_001');
  const datasetQuality = await service.getDatasetQuality('dataset_demo');
  const datasetProfile = await service.getDatasetProfile('dataset_demo');
  const factor = await service.getFactorProfile('factor_demo');
  const model = await service.getModelProfile('model_demo');
  const strategy = await service.getStrategyGovernance('strat_demo');
  const experiment = await service.getExperimentSummary('exp_demo');
  const governance = await service.getSystemGovernanceReport();

  assert.equal(run.resourceUri, 'resource://run/run_demo_001');
  assert.equal(datasetQuality.resourceUri, 'resource://dataset/dataset_demo/quality');
  assert.equal(datasetProfile.resourceUri, 'resource://dataset/dataset_demo/profile');
  assert.equal(factor.resourceUri, 'resource://factor/factor_demo/profile');
  assert.equal(model.resourceUri, 'resource://model/model_demo/profile');
  assert.equal(strategy.resourceUri, 'resource://strategy/strat_demo/governance');
  assert.equal(experiment.resourceUri, 'resource://experiment/exp_demo/summary');
  assert.equal(governance.resourceUri, 'resource://governance/system/report');
  assert.deepEqual(uris, [
    'resource://run/run_demo_001',
    'resource://dataset/dataset_demo/quality',
    'resource://dataset/dataset_demo/profile',
    'resource://factor/factor_demo/profile',
    'resource://model/model_demo/profile',
    'resource://strategy/strat_demo/governance',
    'resource://experiment/exp_demo/summary',
    'resource://governance/system/report',
  ]);
});

test('mcp gateway readResource parses single JSON text content', async () => {
  const service = new McpGatewayService({ get: (_key: string, defaultValue?: string) => defaultValue } as never);
  const internal = service as any;
  const conn = {
    id: 0,
    client: {
      readResource: async ({ uri }: { uri: string }) => ({
        contents: [{ uri, text: '{"count": 1, "name": "tool_catalog"}', mimeType: 'application/json' }],
      }),
    },
    transport: {},
    busy: false,
    connectPromise: null,
  };

  internal.acquire = async () => conn;
  internal.release = () => undefined;

  const result = await service.readResource('resource://server/tool-catalog');

  assert.deepEqual(result, { count: 1, name: 'tool_catalog' });
});
