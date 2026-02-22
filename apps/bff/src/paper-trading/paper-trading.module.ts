import { Module } from '@nestjs/common';
import { PaperTradingController } from './paper-trading.controller';
import { PaperTradingService } from './paper-trading.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { PaperTradingGateway } from './paper-trading.gateway';

@Module({
  imports: [McpGatewayModule],
  controllers: [PaperTradingController],
  providers: [PaperTradingService, PaperTradingGateway],
})
export class PaperTradingModule {}
