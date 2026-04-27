import { Controller, Get, Query, Req, Res } from '@nestjs/common';
import { IsOptional, IsString, Matches } from 'class-validator';
import type { Response } from 'express';
import { FundFlowService } from './fund-flow.service';
import { setFastDataHeaders } from '../common/fast-data-response';

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

type TraceRequest = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
};

@Controller('fund-flow')
export class FundFlowController {
  constructor(private readonly fundFlowService: FundFlowService) {}

  private getTraceId(req: TraceRequest) {
    return String(
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN',
    );
  }

  @Get('stock')
  async getStockFundFlow(@Query() query: StockCodeQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getStockFundFlow(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('sector')
  async getSectorFundFlow(@Req() req: TraceRequest, @Res({ passthrough: true }) res: Response) {
    const data = await this.fundFlowService.getSectorFundFlow();
    setFastDataHeaders(res, data);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('concept')
  async getConceptFundFlow(@Req() req: TraceRequest) {
    const data = await this.fundFlowService.getConceptFundFlow();
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('north')
  async getNorthFund(@Req() req: TraceRequest, @Res({ passthrough: true }) res: Response) {
    const data = await this.fundFlowService.getNorthFund();
    setFastDataHeaders(res, data);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('dragon-tiger')
  async getDragonTiger(@Query() query: OptionalCodeDateDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getDragonTiger(query.date, query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('margin')
  async getMarginData(@Query() query: MarginQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getMarginData(query.code, query.days ? Number(query.days) : 30);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('margin-ranking')
  async getMarginRanking(@Query() query: MarginRankingDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getMarginRanking(query.topN ? Number(query.topN) : 20, query.sortBy ?? 'balance');
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('block-trades')
  async getBlockTrades(@Query() query: BlockTradesDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getBlockTrades(query.date, query.code, query.limit ? Number(query.limit) : 500);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('north-holding')
  async getNorthFundHolding(@Query() query: StockCodeQueryDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getNorthFundHolding(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('north-top')
  async getNorthFundTop(@Query() query: TopNDto, @Req() req: TraceRequest) {
    const data = await this.fundFlowService.getNorthFundTop(query.topN ? Number(query.topN) : 20);
    return { success: true, data, traceId: this.getTraceId(req) };
  }
}
