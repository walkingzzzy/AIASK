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
        return this.optionsService.getOptionChain(symbol);
    }

    @Get('greeks/:symbol')
    async getOptionGreeks(@Param('symbol') symbol: string, @Query() query: OptionGreeksQueryDto) {
        return this.optionsService.getOptionGreeks(symbol, query);
    }

    @Get('smirk/:symbol')
    async getVolatilitySmirk(@Param('symbol') symbol: string) {
        return this.optionsService.getVolatilitySmirk(symbol);
    }
}
