import { Module } from '@nestjs/common';
import { ChatController } from './chat.controller';
import { ChatService } from './chat.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [McpGatewayModule, AuthModule],
  controllers: [ChatController],
  providers: [ChatService],
})
export class ChatModule {}
