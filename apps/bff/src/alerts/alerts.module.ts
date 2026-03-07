import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { WsModule } from '../ws/ws.module';
import { AlertsController } from './alerts.controller';
import { AlertsService } from './alerts.service';

@Module({
  imports: [McpGatewayModule, WsModule],
  controllers: [AlertsController],
  providers: [AlertsService],
})
export class AlertsModule { }
