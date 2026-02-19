import { Module } from '@nestjs/common';
import { McpGatewayService } from './mcp-gateway.service';

@Module({
  providers: [McpGatewayService],
  exports: [McpGatewayService],
})
export class McpGatewayModule {}

