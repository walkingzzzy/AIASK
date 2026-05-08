import { Body, Controller, Delete, Get, Post, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import {
  IsArray,
  IsNumber,
  IsNumberString,
  IsOptional,
  IsString,
  Matches,
  Max,
  Min,
  ValidateNested,
} from 'class-validator';
import { PortfolioService } from './portfolio.service';

class PortfolioStrategyDto {
  @IsString()
  strategyId!: string;

  @Type(() => Number)
  @IsNumber({}, { message: 'weight 必须为数字' })
  @Min(0, { message: 'weight 不能小于 0' })
  @Max(1, { message: 'weight 不能大于 1' })
  weight!: number;
}

class CreatePortfolioDto {
  @IsString()
  name!: string;

  @IsOptional()
  @IsString()
  description?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'initialCapital 必须为数字字符串' })
  initialCapital?: string;

  @IsOptional()
  @IsArray({ message: 'strategies 必须为数组' })
  @ValidateNested({ each: true })
  @Type(() => PortfolioStrategyDto)
  strategies?: PortfolioStrategyDto[];
}

class PortfolioIdDto {
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId!: string;
}

class AddHoldingDto {
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId!: string;

  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsNumberString({}, { message: 'shares 必须为数字字符串' })
  shares!: string;

  @IsOptional()
  @IsNumberString({}, { message: 'costPrice 必须为数字字符串' })
  costPrice?: string;
}

class RemoveHoldingDto {
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId!: string;

  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

@Controller('portfolio')
export class PortfolioController {
  constructor(private readonly portfolioService: PortfolioService) {}

  private userId(req: { user?: { id?: string; sub?: string } }) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  @Get('list')
  async list(@Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } }) {
    const data = await this.portfolioService.list(this.userId(req));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('create')
  async create(
    @Body() body: CreatePortfolioDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.create({
      name: body.name,
      description: body.description,
      initialCapital: body.initialCapital ? Number(body.initialCapital) : undefined,
      strategies: body.strategies?.map((item) => ({
        strategyId: item.strategyId,
        weight: item.weight,
      })),
    }, this.userId(req));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('get')
  async get(
    @Query() query: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.get(Number(query.portfolioId), this.userId(req));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('add-holding')
  async addHolding(
    @Body() body: AddHoldingDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.addHolding({
      portfolioId: Number(body.portfolioId),
      code: body.code,
      shares: Number(body.shares),
      costPrice: body.costPrice != null ? Number(body.costPrice) : undefined,
    }, this.userId(req));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Delete('remove-holding')
  async removeHolding(
    @Query() query: RemoveHoldingDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.removeHolding(Number(query.portfolioId), query.code, this.userId(req));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Delete('delete')
  async deletePortfolio(
    @Query() query: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.delete(Number(query.portfolioId), this.userId(req));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('optimize')
  async optimize(
    @Body() body: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.optimize(Number(body.portfolioId), this.userId(req));
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('risk-analysis')
  async riskAnalysis(
    @Body() body: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.riskAnalysis(Number(body.portfolioId), this.userId(req));
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('stress-test')
  async stressTest(
    @Body() body: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string; sub?: string } },
  ) {
    const data = await this.portfolioService.stressTest(Number(body.portfolioId), this.userId(req));
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
