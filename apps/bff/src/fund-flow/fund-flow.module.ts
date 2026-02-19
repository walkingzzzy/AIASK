import { Module } from '@nestjs/common';
import { FundFlowController } from './fund-flow.controller';
import { FundFlowService } from './fund-flow.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [FundFlowController],
  providers: [FundFlowService],
})
export class FundFlowModule {}
