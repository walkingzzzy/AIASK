import { Controller, Get, Query, Req } from '@nestjs/common';
import { IsOptional, IsString, Matches } from 'class-validator';
import { ResearchService } from './research.service';

class ResearchQueryDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'days 必须为正整数' })
  days?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'startDate 格式必须为 YYYY-MM-DD' })
  startDate?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d{4}-\d{2}-\d{2}$/, { message: 'endDate 格式必须为 YYYY-MM-DD' })
  endDate?: string;

  @IsOptional()
  @IsString()
  keyword?: string;

  @IsOptional()
  @IsString()
  @Matches(/^\d+$/, { message: 'limit 必须为正整数' })
  limit?: string;
}

class NewsQueryDto {
  @IsString() @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' }) code!: string;
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'limit 必须为正整数' }) limit?: string;
}
class MarketNewsQueryDto {
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'limit 必须为正整数' }) limit?: string;
}
class SearchResearchDto {
  @IsOptional() @IsString() keyword?: string;
  @IsOptional() @IsString() code?: string;
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'days 必须为正整数' }) days?: string;
}
class AnalystRankingDto {
  @IsOptional() @IsString() year?: string;
}
class ReportsQueryDto {
  @IsOptional() @IsString() code?: string;
  @IsOptional() @IsString() @Matches(/^\d+$/, { message: 'limit 必须为正整数' }) limit?: string;
}
class MacroIndicatorDto {
  @IsOptional()
  @IsString()
  indicator?: string;
}

class ProfitForecastDto {
  @IsString() @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' }) code!: string;
}

type TraceRequest = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
};

@Controller('research')
export class ResearchController {
  constructor(private readonly researchService: ResearchService) {}

  private getTraceId(req: TraceRequest) {
    return String(
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN',
    );
  }

  @Get('list')
  async getList(@Query() query: ResearchQueryDto, @Req() req: TraceRequest) {
    const data = await this.researchService.getList(query.code, {
      days: query.days ? Number(query.days) : undefined,
      startDate: query.startDate,
      endDate: query.endDate,
      keyword: query.keyword,
      limit: query.limit ? Number(query.limit) : undefined,
    });
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('stock-news')
  async getStockNews(@Query() query: NewsQueryDto, @Req() req: TraceRequest) {
    const data = await this.researchService.getStockNews(query.code, query.limit ? Number(query.limit) : 20);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('market-news')
  async getMarketNews(@Query() query: MarketNewsQueryDto, @Req() req: TraceRequest) {
    const data = await this.researchService.getMarketNews(query.limit ? Number(query.limit) : 20);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('search')
  async searchResearch(@Query() query: SearchResearchDto, @Req() req: TraceRequest) {
    const data = await this.researchService.searchResearch(query.keyword, query.code, query.days ? Number(query.days) : 30);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('analyst-ranking')
  async getAnalystRanking(@Query() query: AnalystRankingDto, @Req() req: TraceRequest) {
    const data = await this.researchService.getAnalystRanking(query.year);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('reports')
  async getReports(@Query() query: ReportsQueryDto, @Req() req: TraceRequest) {
    const data = await this.researchService.getResearchReports(query.code, query.limit ? Number(query.limit) : 10);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('macro')
  async macro(
    @Query() query: MacroIndicatorDto,
    @Req() req: TraceRequest,
  ) {
    const data = await this.researchService.getMacroIndicator(query.indicator);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('profit-forecast')
  async getProfitForecast(@Query() query: ProfitForecastDto, @Req() req: TraceRequest) {
    const data = await this.researchService.getProfitForecast(query.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }
}
