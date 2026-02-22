import { Module } from '@nestjs/common';
import { WsGateway } from './ws.gateway';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule],
  providers: [WsGateway],
  exports: [WsGateway],
})
export class WsModule {}
