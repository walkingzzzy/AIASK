import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { RiskController } from './risk.controller';
import { RiskService } from './risk.service';

@Module({
  imports: [McpGatewayModule],
  controllers: [RiskController],
  providers: [RiskService],
})
export class RiskModule {}

