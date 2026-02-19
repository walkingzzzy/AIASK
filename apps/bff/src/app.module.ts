import { Module } from '@nestjs/common';
import { APP_GUARD, APP_INTERCEPTOR } from '@nestjs/core';
import { ConfigModule } from '@nestjs/config';
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
import { TdxModule } from './tdx/tdx.module';
import { ValuationModule } from './valuation/valuation.module';
import { TechnicalModule } from './technical/technical.module';
import { SentimentModule } from './sentiment/sentiment.module';
import { SearchModule } from './search/search.module';
import { DataModule } from './data/data.module';
import { ChatModule } from './chat/chat.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    DbModule,
    CommonCacheModule,
    McpGatewayModule,
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
    TdxModule,
    ValuationModule,
    TechnicalModule,
    SentimentModule,
    SearchModule,
    DataModule,
    ChatModule,
    AuditModule,
  ],
  providers: [
    { provide: APP_GUARD, useClass: AuthGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
    { provide: APP_INTERCEPTOR, useClass: DegradeInterceptor },
    { provide: APP_INTERCEPTOR, useClass: AuditInterceptor },
  ],
})
export class AppModule {}

