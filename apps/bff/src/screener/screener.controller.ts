import { Controller, Get, Query, UseGuards, UseInterceptors } from '@nestjs/common';
import { ScreenerService } from './screener.service';
import { AuthGuard } from '../rbac/auth.guard';
import { AuditInterceptor } from '../audit/audit.interceptor';

@Controller('v1/screener')
@UseGuards(AuthGuard)
@UseInterceptors(AuditInterceptor)
export class ScreenerController {
    constructor(private readonly screenerService: ScreenerService) { }

    @Get('semantic')
    async semanticSearch(
        @Query('q') query: string,
        @Query('limit') limit?: string
    ) {
        const lim = limit ? parseInt(limit, 10) : 20;
        return this.screenerService.semanticSearch(query, lim);
    }

    @Get('condition')
    async conditionScreen(
        @Query('conditions') conditionsStr: string,
        @Query('limit') limit?: string
    ) {
        const lim = limit ? parseInt(limit, 10) : 50;
        const conditions = conditionsStr ? conditionsStr.split('|') : [];
        return this.screenerService.conditionScreen(conditions, lim);
    }

    @Get('similar')
    async similarStocks(
        @Query('symbol') symbol: string,
        @Query('limit') limit?: string
    ) {
        const lim = limit ? parseInt(limit, 10) : 10;
        return this.screenerService.similarStocks(symbol, lim);
    }
}
