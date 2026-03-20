import 'reflect-metadata';
import * as cookieParser from 'cookie-parser';
import { Controller, Get, ValidationPipe } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AuthController } from '../../src/auth/auth.controller';
import { AuthService } from '../../src/auth/auth.service';
import { PreferencesService } from '../../src/auth/preferences.service';
import { TotpService } from '../../src/auth/totp.service';
import { AuthGuard } from '../../src/rbac/auth.guard';
import { RolesGuard } from '../../src/rbac/roles.guard';
import { Public } from '../../src/rbac/public.decorator';
import { AssistantController } from '../../src/assistant/assistant.controller';
import { AssistantService } from '../../src/assistant/assistant.service';
import { AssistantUnifiedService } from '../../src/assistant/assistant-unified.service';
import { AssistantUnifiedAuditStore } from '../../src/assistant/assistant-unified-audit.store';
import { CommonCacheService } from '../../src/common/cache.service';
import { DbService } from '../../src/db/db.service';
import { McpGatewayService } from '../../src/mcp-gateway/mcp-gateway.service';

export const FIXED_TIME = '2026-03-20T08:00:00.000Z';

@Controller('health')
class UnifiedDecisionTestHealthController {
  @Public()
  @Get()
  getHealth() {
    return {
      success: true,
      service: 'aiask-bff-test',
      status: 'ok',
      db: {
        enabled: false,
        healthy: false,
      },
      timestamp: FIXED_TIME,
    };
  }
}

function createInMemoryDbServiceMock(): Pick<DbService, 'enabled' | 'healthy' | 'query'> {
  return {
    enabled: false,
    healthy: false,
    async query() {
      throw new Error('DATABASE_DISABLED');
    },
  };
}

export function buildMockMcp() {
  return {
    async callTool(name: string) {
      switch (name) {
        case 'get_unified_decision_summary':
          return {
            data: {
              action: 'buy',
              confidence: 0.72,
              final_score: 81,
              summary: '统一决策偏多，适合继续跟踪。',
              reasons: ['基本面改善', '量化胜率回升'],
              risks: ['短线波动放大'],
              gate_flags: [
                {
                  name: 'market_gate',
                  status: 'pass',
                  severity: 'low',
                  blocking: false,
                  message: '未触发市场风险闸门',
                },
              ],
              position_signal: {
                label: '轻仓试探',
                suggested_position_pct: 0.18,
                position_cap_pct: 0.3,
                requested_style: 'balanced',
                user_risk_level: 'balanced',
              },
              data_provenance: [
                { source: 'mcp', dataset: 'unified_decision', timestamp: FIXED_TIME },
              ],
              compliance_notice: '本分析结果仅供参考，不构成投资建议。',
              raw_ai_action: 'buy',
              recommended_horizon: '5-20d',
              updated_at: FIXED_TIME,
              data_quality: { completeness: 0.92, degraded: false },
              fallback_reason: ['event_context partial fallback'],
              details_available: true,
            },
          };
        case 'get_unified_decision_details':
          return {
            data: {
              action: 'buy',
              confidence: 0.72,
              final_score: 81,
              summary: '统一决策偏多，适合继续跟踪。',
              reasons: ['基本面改善', '量化胜率回升'],
              risks: ['短线波动放大'],
              gate_flags: [
                {
                  name: 'market_gate',
                  status: 'pass',
                  severity: 'low',
                  blocking: false,
                  message: '未触发市场风险闸门',
                },
              ],
              compliance_notice: '本分析结果仅供参考，不构成投资建议。',
              updated_at: FIXED_TIME,
              data_quality: { completeness: 0.92, degraded: false },
              fallback_reason: ['event_context partial fallback'],
              details: {
                stock_context: {
                  score: 0.77,
                  current_price: 1688.0,
                  market_snapshot: { liquidity_score: 0.81, spread_pct: 0.12 },
                  fund_flow_snapshot: { main_net_inflow: 120000000, north_hold_ratio: 0.083, flow_bias: 'bullish' },
                  highlights: ['主业盈利能力稳定'],
                  risks: ['估值仍处高位'],
                },
                quant_context: {
                  score: 0.69,
                  reasons: ['RSI 修复', '中短期动量抬升'],
                  probability_targets: {
                    '5d': { up_probability: 0.62 },
                    '20d': { up_probability: 0.58 },
                  },
                  confidence_meta: { sample_size: 48, stability_ratio: 0.74, quality: 'good' },
                },
                event_context: {
                  score: 0.55,
                  event_direction: 'neutral',
                  event_intensity: 'medium',
                  event_horizon: '1-4w',
                  hard_veto_eligible: false,
                  veto_candidates: [],
                  candidate_actions: ['继续观察财报后的资金承接'],
                },
                gate_result: {
                  blocked: false,
                  position_cap_pct: 0.3,
                  user_risk_level: 'balanced',
                  requested_style: 'balanced',
                  flags: ['market_gate pass'],
                },
                fusion: {
                  action: 'buy',
                  final_score: 81,
                  summary: '统一决策偏多，适合继续跟踪。',
                  weights: { stock_context: 0.55, quant: 0.25, event: 0.2 },
                  raw_ai_output: {
                    raw_action: 'buy',
                    raw_summary: '多维证据偏正向。',
                    recommended_horizon: '5-20d',
                  },
                },
              },
            },
          };
        case 'should_i_buy':
          return {
            data: {
              action: 'buy',
              confidence: 0.76,
              summary: '旧入口买入结论',
              reasons: ['旧入口基本面信号偏多'],
              risks: ['旧入口提示波动风险'],
            },
          };
        case 'smart_stock_diagnosis':
          return {
            data: {
              action: 'hold',
              confidence: 0.44,
              summary: '旧入口体检偏中性',
              reasons: ['估值与成长性需要继续确认'],
              risks: ['高波动'],
            },
          };
        case 'decision_manager':
          return {
            data: {
              action: 'watch',
              confidence: 0.41,
              summary: '旧入口决策建议继续观察',
              reasons: ['事件影响尚未完全消化'],
              risks: ['短期交易拥挤'],
            },
          };
        default:
          throw new Error(`unexpected tool: ${name}`);
      }
    },
  };
}

export async function createUnifiedDecisionTestApp(): Promise<INestApplication> {
  const moduleRef = await Test.createTestingModule({
    imports: [ConfigModule.forRoot({ isGlobal: true })],
    controllers: [AuthController, AssistantController, UnifiedDecisionTestHealthController],
    providers: [
      AuthService,
      PreferencesService,
      TotpService,
      AssistantService,
      AssistantUnifiedService,
      AssistantUnifiedAuditStore,
      { provide: DbService, useValue: createInMemoryDbServiceMock() },
      { provide: McpGatewayService, useValue: buildMockMcp() },
      {
        provide: CommonCacheService,
        useValue: {
          get: async () => null,
          set: async () => undefined,
          del: async () => undefined,
        },
      },
    ],
  }).compile();

  const app = moduleRef.createNestApplication();
  app.use(cookieParser());
  app.setGlobalPrefix('api');
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));

  const reflector = app.get(Reflector);
  const authService = app.get(AuthService);
  app.useGlobalGuards(new AuthGuard(reflector, authService), new RolesGuard(reflector));

  return app;
}
