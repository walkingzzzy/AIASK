import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { ArrayMinSize, IsArray, IsIn, IsOptional, IsString, Matches } from 'class-validator';
import { MarketService } from './market.service';

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

@Controller('market')
export class MarketController {
  constructor(private readonly marketService: MarketService) {}

  @Get('quote')
  async getQuote(
    @Query() query: StockCodeQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.marketService.getQuote(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('kline')
  async getKline(
    @Query() query: KlineQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.marketService.getKline(
      query.code,
      query.period ?? 'daily',
      query.limit ? Number(query.limit) : undefined,
    );
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('order-book')
  async getOrderBook(
    @Query() query: StockCodeQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.marketService.getOrderBook(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return {
      success: true,
      data,
      traceId: String(traceId),
    };
  }

  @Get('stock-list')
  async getStockList(@Req() req: any) {
    const data = await this.marketService.getStockList();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('batch-quotes')
  async getBatchQuotes(@Body() body: BatchQuotesDto, @Req() req: any) {
    const data = await this.marketService.getBatchQuotes(body.codes);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('index-batch-quotes')
  async getIndexBatchQuotes(@Body() body: BatchQuotesDto, @Req() req: any) {
    const data = await this.marketService.getIndexBatchQuotes(body.codes);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('minute-kline')
  async getMinuteKline(@Query() query: MinuteKlineQueryDto, @Req() req: any) {
    const data = await this.marketService.getMinuteKline(query.code, query.period ?? '5m', query.limit ? Number(query.limit) : 300);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('index-quote')
  async getIndexQuote(@Query() query: IndexCodeQueryDto, @Req() req: any) {
    const data = await this.marketService.getIndexQuote(query.indexCode);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('trade-details')
  async getTradeDetails(@Query() query: TradeDetailsQueryDto, @Req() req: any) {
    const data = await this.marketService.getTradeDetails(query.code, query.limit ? Number(query.limit) : 20);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('limit-up')
  async getLimitUp(@Query() query: DateQueryDto, @Req() req: any) {
    const data = await this.marketService.getLimitUpStocks(query.date);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('limit-up-stats')
  async getLimitUpStats(@Query() query: DateQueryDto, @Req() req: any) {
    const data = await this.marketService.getLimitUpStats(query.date);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('blocks')
  async getBlocks(@Query() query: BlocksQueryDto, @Req() req: any) {
    const data = await this.marketService.getMarketBlocks(query.blockType ?? 'industry', query.limit ? Number(query.limit) : undefined);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('block-stocks')
  async getBlockStocks(@Query() query: BlockCodeQueryDto, @Req() req: any) {
    const data = await this.marketService.getBlockStocks(query.blockCode);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('search')
  async searchStocks(@Query() query: SearchQueryDto, @Req() req: any) {
    const data = await this.marketService.searchStocks(query.keyword, query.limit ? Number(query.limit) : 20);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
