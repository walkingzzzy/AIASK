import { Module } from '@nestjs/common';
import { MarketController } from './market.controller';
import { MarketService } from './market.service';
import { MarketScheduler } from './market.scheduler';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { WsModule } from '../ws/ws.module';

@Module({
  imports: [McpGatewayModule, WsModule],
  controllers: [MarketController],
  providers: [MarketService, MarketScheduler],
  exports: [MarketService],
})
export class MarketModule { }
