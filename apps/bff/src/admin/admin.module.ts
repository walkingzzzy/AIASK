import { Module } from '@nestjs/common';
import { AdminController } from './admin.controller';
import { AdminService } from './admin.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { CommonCacheModule } from '../common/cache.module';
import { AuthModule } from '../auth/auth.module';
import { AuditModule } from '../audit/audit.module';

@Module({
  imports: [McpGatewayModule, CommonCacheModule, AuthModule, AuditModule],
  controllers: [AdminController],
  providers: [AdminService],
})
export class AdminModule {}
