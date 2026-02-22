import { Module } from '@nestjs/common';
import { StrategyMarketController } from './strategy.controller';
import { StrategyMarketService } from './strategy.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [StrategyMarketController],
  providers: [StrategyMarketService],
})
export class StrategyModule {}
