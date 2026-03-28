import { Module } from '@nestjs/common';
import { ExecutionController } from './execution.controller';
import { ExecutionService } from './execution.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { PaperTradingModule } from '../paper-trading/paper-trading.module';

@Module({
  imports: [PaperTradingModule, McpGatewayModule],
  controllers: [ExecutionController],
  providers: [ExecutionService],
})
export class ExecutionModule {}
