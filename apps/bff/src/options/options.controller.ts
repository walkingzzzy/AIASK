import { Controller, Get, Param, Query, UseGuards, UseInterceptors } from '@nestjs/common';
import { IsIn, IsNumberString, IsOptional, IsString } from 'class-validator';
import { OptionsService } from './options.service';
import { AuthGuard } from '../rbac/auth.guard';
import { AuditInterceptor } from '../audit/audit.interceptor';

class OptionGreeksQueryDto {
    @IsOptional()
    @IsIn(['call', 'put'])
    optionType?: 'call' | 'put';

    @IsOptional()
    @IsNumberString()
    strike?: string;

    @IsOptional()
    @IsNumberString()
    spot?: string;

    @IsOptional()
    @IsNumberString()
    volatility?: string;

    @IsOptional()
    @IsNumberString()
    riskFreeRate?: string;

    @IsOptional()
    @IsNumberString()
    timeToMaturity?: string;

    @IsOptional()
    @IsNumberString()
    dividendYield?: string;

    @IsOptional()
    @IsString()
    expiryDate?: string;
}

@Controller('v1/options')
@UseGuards(AuthGuard)
@UseInterceptors(AuditInterceptor)
export class OptionsController {
    constructor(private readonly optionsService: OptionsService) { }

    @Get('chain/:symbol')
    async getOptionChain(@Param('symbol') symbol: string) {
        const data = await this.optionsService.getOptionChain(symbol);
        return { success: true, data };
    }

    @Get('greeks/:symbol')
    async getOptionGreeks(@Param('symbol') symbol: string, @Query() query: OptionGreeksQueryDto) {
        const data = await this.optionsService.getOptionGreeks(symbol, query);
        return { success: true, data };
    }

    @Get('smirk/:symbol')
    async getVolatilitySmirk(@Param('symbol') symbol: string) {
        const data = await this.optionsService.getVolatilitySmirk(symbol);
        return { success: true, data };
    }
}
