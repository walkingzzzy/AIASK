import { Module, forwardRef } from '@nestjs/common';
import { WsGateway } from './ws.gateway';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { MarketModule } from '../market/market.module';

@Module({
  imports: [McpGatewayModule, forwardRef(() => MarketModule)],
  providers: [WsGateway],
  exports: [WsGateway],
})
export class WsModule {}
