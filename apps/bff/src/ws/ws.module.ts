import { Module, forwardRef } from '@nestjs/common';
import { WsGateway } from './ws.gateway';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { MarketModule } from '../market/market.module';
import { AuthModule } from '../auth/auth.module';
import { PaperTradingModule } from '../paper-trading/paper-trading.module';

@Module({
  imports: [
    McpGatewayModule,
    AuthModule,
    PaperTradingModule,
    forwardRef(() => MarketModule),
  ],
  providers: [WsGateway],
  exports: [WsGateway],
})
export class WsModule {}
