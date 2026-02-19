import { Controller, Get, Query, Req } from '@nestjs/common';
import { IsOptional, IsString, Matches } from 'class-validator';
import { FundFlowService } from './fund-flow.service';

class StockCodeQueryDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

class OptionalCodeDateDto {
  @IsOptional() @IsString() code?: string;
  @IsOptional() @IsString() date?: string;
}
class MarginQueryDto {
  @IsOptional() @IsString() code?: string;
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'days 必须为正整数' }) days?: string;
}
class MarginRankingDto {
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'topN 必须为正整数' }) topN?: string;
  @IsOptional() @IsString() sortBy?: string;
}
class BlockTradesDto {
  @IsOptional() @IsString() date?: string;
  @IsOptional() @IsString() code?: string;
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'limit 必须为正整数' }) limit?: string;
}
class TopNDto {
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'topN 必须为正整数' }) topN?: string;
}

@Controller('fund-flow')
export class FundFlowController {
  constructor(private readonly fundFlowService: FundFlowService) {}

  @Get('stock')
  async getStockFundFlow(
    @Query() query: StockCodeQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundFlowService.getStockFundFlow(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('sector')
  async getSectorFundFlow(
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundFlowService.getSectorFundFlow();
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('concept')
  async getConceptFundFlow(
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundFlowService.getConceptFundFlow();
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('north')
  async getNorthFund(
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.fundFlowService.getNorthFund();
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('dragon-tiger')
  async getDragonTiger(@Query() query: OptionalCodeDateDto, @Req() req: any) {
    const data = await this.fundFlowService.getDragonTiger(query.date, query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('margin')
  async getMarginData(@Query() query: MarginQueryDto, @Req() req: any) {
    const data = await this.fundFlowService.getMarginData(query.code, query.days ? Number(query.days) : 30);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('margin-ranking')
  async getMarginRanking(@Query() query: MarginRankingDto, @Req() req: any) {
    const data = await this.fundFlowService.getMarginRanking(query.topN ? Number(query.topN) : 20, query.sortBy ?? 'balance');
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('block-trades')
  async getBlockTrades(@Query() query: BlockTradesDto, @Req() req: any) {
    const data = await this.fundFlowService.getBlockTrades(query.date, query.code, query.limit ? Number(query.limit) : 500);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('north-holding')
  async getNorthFundHolding(@Query() query: StockCodeQueryDto, @Req() req: any) {
    const data = await this.fundFlowService.getNorthFundHolding(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('north-top')
  async getNorthFundTop(@Query() query: TopNDto, @Req() req: any) {
    const data = await this.fundFlowService.getNorthFundTop(query.topN ? Number(query.topN) : 20);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
