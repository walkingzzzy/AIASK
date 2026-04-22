import { Module } from '@nestjs/common';
import { ChatController } from './chat.controller';
import { ChatService } from './chat.service';
import { UserContextService } from './user-context.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { AuthModule } from '../auth/auth.module';
import { BehaviorModule } from '../behavior/behavior.module';

@Module({
  imports: [McpGatewayModule, AuthModule, BehaviorModule],
  controllers: [ChatController],
  providers: [ChatService, UserContextService],
  exports: [ChatService],
})
export class ChatModule { }
