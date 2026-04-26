import { Module } from '@nestjs/common';
import { StrategyMarketController } from './strategy.controller';
import { StrategyFactoryController } from './strategy-factory.controller';
import { StrategyIncubationController } from './strategy-incubation.controller';
import { StrategyRiskController } from './strategy-risk.controller';
import { StrategyVectorController } from './strategy-vector.controller';
import { StrategyOperatorController } from './strategy-operator.controller';
import { StrategyMarketService } from './strategy.service';
import { StrategyOperatorService } from './strategy-operator.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { McpJobsModule } from '../mcp-jobs/mcp-jobs.module';
import { PaperTradingModule } from '../paper-trading/paper-trading.module';
import { DbModule } from '../db/db.module';

@Module({
  imports: [McpGatewayModule, McpJobsModule, PaperTradingModule, DbModule],
  controllers: [
    StrategyFactoryController,
    StrategyIncubationController,
    StrategyRiskController,
    StrategyVectorController,
    StrategyOperatorController,
    StrategyMarketController,
  ],
  providers: [StrategyMarketService, StrategyOperatorService],
})
export class StrategyModule {}
