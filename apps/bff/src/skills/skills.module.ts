import { Module } from '@nestjs/common';
import { SkillsController } from './skills.controller';
import { SkillsService } from './skills.service';
import { CommonCacheModule } from '../common/cache.module';
import { AuthModule } from '../auth/auth.module';
import { AuditModule } from '../audit/audit.module';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';

@Module({
    imports: [CommonCacheModule, AuthModule, AuditModule, McpGatewayModule],
    controllers: [SkillsController],
    providers: [SkillsService],
    exports: [SkillsService],
})
export class SkillsModule { }
