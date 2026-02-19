import { Module } from '@nestjs/common';
import { ValuationController } from './valuation.controller';
import { ValuationService } from './valuation.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [ValuationController],
  providers: [ValuationService],
})
export class ValuationModule {}
