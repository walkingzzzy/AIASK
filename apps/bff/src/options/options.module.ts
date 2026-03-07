import { Module } from '@nestjs/common';
import { OptionsController } from './options.controller';
import { OptionsService } from './options.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { CommonCacheModule } from '../common/cache.module';
import { AuthModule } from '../auth/auth.module';
import { AuditModule } from '../audit/audit.module';

@Module({
    imports: [McpGatewayModule, CommonCacheModule, AuthModule, AuditModule],
    controllers: [OptionsController],
    providers: [OptionsService],
    exports: [OptionsService],
})
export class OptionsModule { }
