import { Module } from '@nestjs/common';
import { MacroController } from './macro.controller';
import { MacroService } from './macro.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { CommonCacheModule } from '../common/cache.module';
import { AuthModule } from '../auth/auth.module';
import { AuditModule } from '../audit/audit.module';

@Module({
    imports: [McpGatewayModule, CommonCacheModule, AuthModule, AuditModule],
    controllers: [MacroController],
    providers: [MacroService],
    exports: [MacroService],
})
export class MacroModule { }
