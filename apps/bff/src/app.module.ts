import { Module } from '@nestjs/common';
import { APP_GUARD, APP_INTERCEPTOR } from '@nestjs/core';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { ThrottlerModule } from '@nestjs/throttler';
import { HealthModule } from './health/health.module';
import { McpGatewayModule } from './mcp-gateway/mcp-gateway.module';
import { AuthModule } from './auth/auth.module';
import { AuthGuard } from './rbac/auth.guard';
import { RolesGuard } from './rbac/roles.guard';
import { AuditInterceptor } from './audit/audit.interceptor';
import { MarketModule } from './market/market.module';
import { AuditModule } from './audit/audit.module';
import { FundamentalModule } from './fundamental/fundamental.module';
import { ResearchModule } from './research/research.module';
import { AlertsModule } from './alerts/alerts.module';
import { CommonCacheModule } from './common/cache.module';
import { DbModule } from './db/db.module';
import { DegradeInterceptor } from './common/degrade.interceptor';
import { BacktestModule } from './backtest/backtest.module';
import { PortfolioModule } from './portfolio/portfolio.module';
import { RiskModule } from './risk/risk.module';
import { FundFlowModule } from './fund-flow/fund-flow.module';
import { FactorModule } from './factor/factor.module';
import { AssistantModule } from './assistant/assistant.module';
import { AnalysisModule } from './analysis/analysis.module';
import { ValuationModule } from './valuation/valuation.module';
import { TechnicalModule } from './technical/technical.module';
import { SentimentModule } from './sentiment/sentiment.module';
import { SearchModule } from './search/search.module';
import { DataModule } from './data/data.module';
import { ChatModule } from './chat/chat.module';
import { StrategyModule } from './strategy/strategy.module';
import { PaperTradingModule } from './paper-trading/paper-trading.module';
import { WsModule } from './ws/ws.module';
import { OptionsModule } from './options/options.module';
import { MacroModule } from './macro/macro.module';
import { ScreenerModule } from './screener/screener.module';
import { SkillsModule } from './skills/skills.module';
import { TradingThrottleGuard } from './common/trading-throttle.guard';
import { WatchlistModule } from './watchlist/watchlist.module';
import { NotificationModule } from './notification/notification.module';
import { ExportModule } from './export/export.module';
import { AdminModule } from './admin/admin.module';
import { EventModule } from './event/event.module';
import { ExecutionModule } from './execution/execution.module';
import { PerformanceModule } from './performance/performance.module';
import { WorkspaceModule } from './workspace/workspace.module';
import { ObservabilityModule } from './observability/observability.module';
import { ObservabilityInterceptor } from './observability/observability.interceptor';
import { McpJobsModule } from './mcp-jobs/mcp-jobs.module';

const DEFAULT_HTTP_THROTTLE_TTL_MS = 60_000;
const DEFAULT_HTTP_THROTTLE_LIMIT = 600;

function readPositiveInt(value: string | undefined, fallback: number) {
  const parsed = Number.parseInt(value ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    ObservabilityModule,
    ThrottlerModule.forRootAsync({
      inject: [ConfigService],
      useFactory: (config: ConfigService) => {
        const ttl = readPositiveInt(
          config.get<string>('HTTP_THROTTLE_TTL_MS')
            ?? config.get<string>('THROTTLE_TTL_MS'),
          DEFAULT_HTTP_THROTTLE_TTL_MS,
        );
        const limit = readPositiveInt(
          config.get<string>('HTTP_THROTTLE_LIMIT')
            ?? config.get<string>('THROTTLE_LIMIT'),
          DEFAULT_HTTP_THROTTLE_LIMIT,
        );

        return [{ ttl, limit }];
      },
    }),
    DbModule,
    CommonCacheModule,
    McpGatewayModule,
    McpJobsModule,
    AuthModule,
    HealthModule,
    MarketModule,
    FundamentalModule,
    ResearchModule,
    AlertsModule,
    BacktestModule,
    PortfolioModule,
    RiskModule,
    FundFlowModule,
    FactorModule,
    AssistantModule,
    AnalysisModule,
    ValuationModule,
    TechnicalModule,
    SentimentModule,
    SearchModule,
    DataModule,
    ChatModule,
    AuditModule,
    StrategyModule,
    PaperTradingModule,
    WsModule,
    OptionsModule,
    MacroModule,
    ScreenerModule,
    SkillsModule,
    WatchlistModule,
    NotificationModule,
    EventModule,
    ExecutionModule,
    PerformanceModule,
    WorkspaceModule,
    ExportModule,
    AdminModule,
  ],
  providers: [
    { provide: APP_GUARD, useClass: AuthGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
    { provide: APP_GUARD, useClass: TradingThrottleGuard },
    { provide: APP_INTERCEPTOR, useClass: ObservabilityInterceptor },
    { provide: APP_INTERCEPTOR, useClass: DegradeInterceptor },
    { provide: APP_INTERCEPTOR, useClass: AuditInterceptor },
  ],
})
export class AppModule { }
