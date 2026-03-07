import { Body, Controller, Delete, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsOptional, IsString, Matches } from 'class-validator';
import { WatchlistService } from './watchlist.service';

class AddStocksDto {
    @IsString()
    group!: string;

    @IsArray()
    @IsString({ each: true })
    codes!: string[];
}

class RemoveStockDto {
    @IsString()
    group!: string;

    @IsString()
    @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
    code!: string;
}

class CreateGroupDto {
    @IsString()
    name!: string;

    @IsOptional()
    @IsString()
    color?: string;
}

class DeleteGroupDto {
    @IsString()
    name!: string;
}

class ReorderDto {
    @IsString()
    group!: string;

    @IsArray()
    @IsString({ each: true })
    codes!: string[];
}

@Controller('watchlist')
export class WatchlistController {
    constructor(private readonly watchlistService: WatchlistService) { }

    @Get('groups')
    async listGroups(
        @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } },
    ) {
        const userId = req.user?.id ?? 'default';
        const data = await this.watchlistService.listGroups(userId);
        return { success: true, data, traceId: this.getTraceId(req) };
    }

    @Post('groups/create')
    async createGroup(
        @Body() body: CreateGroupDto,
        @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } },
    ) {
        const userId = req.user?.id ?? 'default';
        const data = await this.watchlistService.createGroup(userId, body.name, body.color);
        return { success: true, data, traceId: this.getTraceId(req) };
    }

    @Delete('groups/delete')
    async deleteGroup(
        @Query() query: DeleteGroupDto,
        @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } },
    ) {
        const userId = req.user?.id ?? 'default';
        const data = await this.watchlistService.deleteGroup(userId, query.name);
        return { success: true, data, traceId: this.getTraceId(req) };
    }

    @Post('stocks/add')
    async addStocks(
        @Body() body: AddStocksDto,
        @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } },
    ) {
        const userId = req.user?.id ?? 'default';
        const data = await this.watchlistService.addStocks(userId, body.group, body.codes);
        return { success: true, data, traceId: this.getTraceId(req) };
    }

    @Delete('stocks/remove')
    async removeStock(
        @Query() query: RemoveStockDto,
        @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } },
    ) {
        const userId = req.user?.id ?? 'default';
        const data = await this.watchlistService.removeStock(userId, query.group, query.code);
        return { success: true, data, traceId: this.getTraceId(req) };
    }

    @Post('stocks/reorder')
    async reorderStocks(
        @Body() body: ReorderDto,
        @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } },
    ) {
        const userId = req.user?.id ?? 'default';
        const data = await this.watchlistService.reorderStocks(userId, body.group, body.codes);
        return { success: true, data, traceId: this.getTraceId(req) };
    }

    private getTraceId(req: { traceId?: string; headers?: Record<string, string | undefined> }): string {
        return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
    }
}
