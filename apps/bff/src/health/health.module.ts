import { Module } from '@nestjs/common';
import { AuditModule } from '../audit/audit.module';
import { NotificationModule } from '../notification/notification.module';
import { HealthController } from './health.controller';
import { HealthService } from './health.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
  imports: [McpGatewayModule, AuditModule, NotificationModule],
  controllers: [HealthController],
  providers: [HealthService],
})
export class HealthModule {}
