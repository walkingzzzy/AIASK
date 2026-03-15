import { Module } from '@nestjs/common';
import { PaperTradingController } from './paper-trading.controller';
import { PaperTradingService } from './paper-trading.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { PaperTradingGateway } from './paper-trading.gateway';
import { AuthModule } from '../auth/auth.module';
import { PaperTradingIdempotencyService } from './paper-trading-idempotency.service';

@Module({
  imports: [McpGatewayModule, AuthModule],
  controllers: [PaperTradingController],
  providers: [PaperTradingService, PaperTradingGateway, PaperTradingIdempotencyService],
  exports: [PaperTradingService],
})
export class PaperTradingModule {}
