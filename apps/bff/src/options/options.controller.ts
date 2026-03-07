import { Controller, Get, Param, UseGuards, UseInterceptors } from '@nestjs/common';
import { OptionsService } from './options.service';
import { AuthGuard } from '../rbac/auth.guard';
import { AuditInterceptor } from '../audit/audit.interceptor';

@Controller('v1/options')
@UseGuards(AuthGuard)
@UseInterceptors(AuditInterceptor)
export class OptionsController {
    constructor(private readonly optionsService: OptionsService) { }

    @Get('chain/:symbol')
    async getOptionChain(@Param('symbol') symbol: string) {
        return this.optionsService.getOptionChain(symbol);
    }

    @Get('greeks/:symbol')
    async getOptionGreeks(@Param('symbol') symbol: string) {
        return this.optionsService.getOptionGreeks(symbol);
    }

    @Get('smirk/:symbol')
    async getVolatilitySmirk(@Param('symbol') symbol: string) {
        return this.optionsService.getVolatilitySmirk(symbol);
    }
}
