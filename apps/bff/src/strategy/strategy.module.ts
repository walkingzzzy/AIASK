import { Module } from '@nestjs/common';
import { StrategyMarketController } from './strategy.controller';
import { StrategyFactoryController } from './strategy-factory.controller';
import { StrategyIncubationController } from './strategy-incubation.controller';
import { StrategyRiskController } from './strategy-risk.controller';
import { StrategyVectorController } from './strategy-vector.controller';
import { StrategyMarketService } from './strategy.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [
    StrategyMarketController,
    StrategyFactoryController,
    StrategyIncubationController,
    StrategyRiskController,
    StrategyVectorController,
  ],
  providers: [StrategyMarketService],
})
export class StrategyModule {}
