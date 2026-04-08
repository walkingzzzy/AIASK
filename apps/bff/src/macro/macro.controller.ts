import { Controller, Get, Param, UseGuards, UseInterceptors } from '@nestjs/common';
import { MacroService } from './macro.service';
import { AuthGuard } from '../rbac/auth.guard';
import { AuditInterceptor } from '../audit/audit.interceptor';

@Controller('v1/macro')
@UseGuards(AuthGuard)
@UseInterceptors(AuditInterceptor)
export class MacroController {
    constructor(private readonly macroService: MacroService) { }

    @Get('indicator/:name')
    async getMacroIndicator(@Param('name') name: string) {
        const data = await this.macroService.getMacroIndicator(name);
        return { success: true, data };
    }
}
