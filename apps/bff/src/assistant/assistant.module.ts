import { Module } from '@nestjs/common';
import { AssistantController } from './assistant.controller';
import { AssistantService } from './assistant.service';
import { AssistantUnifiedService } from './assistant-unified.service';
import { AssistantUnifiedAuditStore } from './assistant-unified-audit.store';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  controllers: [AssistantController],
  providers: [AssistantService, AssistantUnifiedService, AssistantUnifiedAuditStore],
})
export class AssistantModule {}
