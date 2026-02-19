import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { AlertsController } from './alerts.controller';
import { AlertsService } from './alerts.service';

@Module({
  imports: [McpGatewayModule],
  controllers: [AlertsController],
  providers: [AlertsService],
})
export class AlertsModule {}

