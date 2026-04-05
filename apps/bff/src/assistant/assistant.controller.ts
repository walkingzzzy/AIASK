import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import { IsBoolean, IsNumber, IsOptional, IsString, Matches, Min } from 'class-validator';
import { AssistantUnifiedService } from './assistant-unified.service';
import { AssistantService } from './assistant.service';
import { UnifiedDecisionBodyDto, UnifiedDecisionDiffQueryDto } from './dto/unified-decision.dto';

class StockCodeBodyDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

class StockWorkflowBodyDto extends StockCodeBodyDto {
  @IsOptional() @IsString() investmentStyle?: string;
  @IsOptional() @Type(() => Boolean) @IsBoolean() includeKline?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() includeFinancials?: boolean;
  @IsOptional() @Type(() => Boolean) @IsBoolean() includeDecision?: boolean;
  @IsOptional() @Type(() => Number) @IsNumber() @Min(20) klineLimit?: number;
  @IsOptional() @IsString() asOf?: string;
}

class IndustryChainDto {
  @IsOptional() @IsString() keyword?: string;
  @IsOptional() @IsString() chainId?: string;
}
class DailyReportDto {
  @IsOptional() @IsString() date?: string;
}
class SellDecisionBodyDto extends StockCodeBodyDto {
  @Type(() => Number)
  @IsNumber({}, { message: 'buyPrice 必须为数字' })
  @Min(0.01, { message: 'buyPrice 必须大于 0' })
  buyPrice!: number;

  @Type(() => Number)
  @IsOptional()
  @IsNumber({}, { message: 'holdingDays 必须为数字' })
  @Min(0, { message: 'holdingDays 不能为负数' })
  holdingDays?: number;
}

@Controller('assistant')
export class AssistantController {
  constructor(
    private readonly assistantService: AssistantService,
    private readonly assistantUnifiedService: AssistantUnifiedService,
  ) {}

  private getTraceId(req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    return String(
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN',
    );
  }

  private getUserId(req: { user?: { sub?: string; id?: string } }) {
    return String(req.user?.sub ?? req.user?.id ?? '').trim();
  }

  @Post('diagnosis')
  async diagnosis(
    @Body() body: StockCodeBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.diagnosis(body.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('analysis-workflow')
  async analysisWorkflow(
    @Body() body: StockWorkflowBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.analyzeWorkflow(body.code, {
      investmentStyle: body.investmentStyle,
      includeKline: body.includeKline,
      includeFinancials: body.includeFinancials,
      includeDecision: body.includeDecision,
      klineLimit: body.klineLimit,
      asOf: body.asOf,
    });
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('should-buy')
  async shouldBuy(
    @Body() body: StockCodeBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.shouldBuy(body.code);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('should-sell')
  async shouldSell(
    @Body() body: SellDecisionBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.shouldSell(body.code, body.buyPrice, body.holdingDays);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('unified-decision')
  async unifiedDecision(
    @Body() body: UnifiedDecisionBodyDto,
    @Req() req: {
      user?: { sub?: string; id?: string };
      traceId?: string;
      headers?: Record<string, string | undefined>;
    },
  ) {
    const userId = this.getUserId(req);
    const data = await this.assistantUnifiedService.getUnifiedDecisionSummary(
      body.code,
      body.investmentStyle ?? 'balanced',
      userId || undefined,
      Boolean(body.legacyMode),
      this.getTraceId(req),
    );
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('unified-decision/details')
  async unifiedDecisionDetails(
    @Body() body: UnifiedDecisionBodyDto,
    @Req() req: {
      user?: { sub?: string; id?: string };
      traceId?: string;
      headers?: Record<string, string | undefined>;
    },
  ) {
    const userId = this.getUserId(req);
    const data = await this.assistantUnifiedService.getUnifiedDecisionDetails(
      body.code,
      body.investmentStyle ?? 'balanced',
      userId || undefined,
      Boolean(body.legacyMode),
      this.getTraceId(req),
    );
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Get('unified-decision/diff-logs')
  async unifiedDecisionDiffLogs(
    @Query() query: UnifiedDecisionDiffQueryDto,
    @Req() req: {
      user?: { sub?: string; id?: string };
      traceId?: string;
      headers?: Record<string, string | undefined>;
    },
  ) {
    const userId = this.getUserId(req);
    const data = await this.assistantUnifiedService.getUnifiedDecisionDiffLogs(userId, {
      limit: query.limit,
      stockCode: query.code,
      actionAlignment: query.actionAlignment,
    });
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('industry-chain')
  async getIndustryChain(
    @Body() body: IndustryChainDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.getIndustryChain(body.keyword, body.chainId);
    return { success: true, data, traceId: this.getTraceId(req) };
  }

  @Post('daily-report')
  async generateDailyReport(
    @Body() body: DailyReportDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.generateDailyReport(body.date);
    return { success: true, data, traceId: this.getTraceId(req) };
  }
}
