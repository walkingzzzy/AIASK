import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { BacktestController } from './backtest.controller';
import { BacktestService } from './backtest.service';

@Module({
  imports: [McpGatewayModule],
  controllers: [BacktestController],
  providers: [BacktestService],
})
export class BacktestModule {}

