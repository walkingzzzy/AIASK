import { Module } from '@nestjs/common';
import { ScreenerController } from './screener.controller';
import { ScreenerService } from './screener.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { CommonCacheModule } from '../common/cache.module';
import { AuthModule } from '../auth/auth.module';
import { AuditModule } from '../audit/audit.module';

@Module({
    imports: [McpGatewayModule, CommonCacheModule, AuthModule, AuditModule],
    controllers: [ScreenerController],
    providers: [ScreenerService],
    exports: [ScreenerService],
})
export class ScreenerModule { }
