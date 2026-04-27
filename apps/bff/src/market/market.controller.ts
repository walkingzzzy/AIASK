import { Body, Controller, Get, Post, Query, Req, Res } from '@nestjs/common';
import { ArrayMinSize, IsArray, IsIn, IsOptional, IsString, Matches } from 'class-validator';
import type { Response } from 'express';
import { MarketService } from './market.service';
import { setFastDataHeaders } from '../common/fast-data-response';

class StockCodeQueryDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

class KlineQueryDto extends StockCodeQueryDto {
  @IsOptional()
  @IsString()
  @IsIn(['daily', 'weekly', 'monthly'], { message: 'period 仅支持 daily/weekly/monthly' })
  period?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'limit 必须为正整数' })
  limit?: string;
}

class MinuteKlineQueryDto extends StockCodeQueryDto {
  @IsOptional()
  @IsString()
  @IsIn(['1m', '5m', '15m', '30m', '60m'], { message: 'period 仅支持 1m/5m/15m/30m/60m' })
  period?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'limit 必须为正整数' })
  limit?: string;
}

class IndexCodeQueryDto {
  @IsString()
  indexCode!: string;
}

class TradeDetailsQueryDto extends StockCodeQueryDto {
  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'limit 必须为正整数' })
  limit?: string;
}

class DateQueryDto {
  @IsOptional()
  @IsString()
  date?: string;
}

class BlocksQueryDto {
  @IsOptional()
  @IsString()
  @IsIn(['industry', 'concept', 'region'], { message: 'blockType 仅支持 industry/concept/region' })
  blockType?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'limit 必须为正整数' })
  limit?: string;
}

class BlockCodeQueryDto {
  @IsString()
  blockCode!: string;
}

class SearchQueryDto {
  @IsString()
  keyword!: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'limit 必须为正整数' })
  limit?: string;
}

class BatchQuotesDto {
  @IsArray()
  @ArrayMinSize(1)
  codes!: string[];
}

type TraceRequest = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
};

@Controller('market')
export class MarketController {
  constructor(private readonly marketService: MarketService) {}

  private getTraceId(req: TraceRequest) {
    return String(
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN',
    );
  }

  @Get('quote')
  async getQuote(@Query() query: StockCodeQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getQuote(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('kline')
  async getKline(@Query() query: KlineQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getKline(
      query.code,
      query.period ?? 'daily',
      query.limit ? Number(query.limit) : undefined,
    );
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('order-book')
  async getOrderBook(@Query() query: StockCodeQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getOrderBook(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('stock-list')
  async getStockList(@Req() req: TraceRequest) {
    const data = await this.marketService.getStockList();
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('batch-quotes')
  async getBatchQuotes(@Body() body: BatchQuotesDto, @Req() req: TraceRequest, @Res({ passthrough: true }) res: Response) {
    const data = await this.marketService.getBatchQuotes(body.codes);
    setFastDataHeaders(res, data);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('index-batch-quotes')
  async getIndexBatchQuotes(@Body() body: BatchQuotesDto, @Req() req: TraceRequest, @Res({ passthrough: true }) res: Response) {
    const data = await this.marketService.getIndexBatchQuotes(body.codes);
    setFastDataHeaders(res, data);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('minute-kline')
  async getMinuteKline(@Query() query: MinuteKlineQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getMinuteKline(query.code, query.period ?? '5m', query.limit ? Number(query.limit) : 300);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('index-quote')
  async getIndexQuote(@Query() query: IndexCodeQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getIndexQuote(query.indexCode);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('trade-details')
  async getTradeDetails(@Query() query: TradeDetailsQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getTradeDetails(query.code, query.limit ? Number(query.limit) : 20);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('limit-up')
  async getLimitUp(@Query() query: DateQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getLimitUpStocks(query.date);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('limit-up-stats')
  async getLimitUpStats(@Query() query: DateQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getLimitUpStats(query.date);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('blocks')
  async getBlocks(@Query() query: BlocksQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getMarketBlocks(query.blockType ?? 'industry', query.limit ? Number(query.limit) : undefined);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('block-stocks')
  async getBlockStocks(@Query() query: BlockCodeQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.getBlockStocks(query.blockCode);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('search')
  async searchStocks(@Query() query: SearchQueryDto, @Req() req: TraceRequest) {
    const data = await this.marketService.searchStocks(query.keyword, query.limit ? Number(query.limit) : 20);
    return { success: true, data, traceId: this.getTraceId(req) };
  }
}
