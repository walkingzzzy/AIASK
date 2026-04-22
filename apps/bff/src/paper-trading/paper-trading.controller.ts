import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsInt, IsNumber, IsOptional, IsString, Min } from 'class-validator';
import { Type } from 'class-transformer';
import { Throttle } from '@nestjs/throttler';
import { PaperTradingService } from './paper-trading.service';

class PlaceOrderDto {
  @IsString() code!: string;
  @IsString() direction!: string;
  @Type(() => Number) @IsInt() @Min(1) quantity!: number;
  @IsOptional() @Type(() => Number) @IsNumber() price?: number;
  @IsOptional() @IsString() order_type?: string;
  @IsOptional() @Type(() => Number) @IsNumber() stop_price?: number;
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @IsString() idempotency_key?: string;
}

class CancelOrderDto {
  @IsString() order_id!: string;
  @IsOptional() @IsString() idempotency_key?: string;
}

class UpdatePricesDto {
  @IsOptional() @IsString() account_id?: string;
}

class ReconcileDto {
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() refresh_prices?: boolean;
  @IsOptional() force?: boolean;
}

class RiskRulesDto {
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @Type(() => Number) @IsNumber() max_position_pct?: number;
  @IsOptional() @Type(() => Number) @IsNumber() max_drawdown_pct?: number;
  @IsOptional() @Type(() => Number) @IsNumber() stop_loss_pct?: number;
}

class ComplianceCheckDto {
  @IsString() code!: string;
  @IsString() direction!: string;
  @Type(() => Number) @IsInt() @Min(1) quantity!: number;
  @IsOptional() @Type(() => Number) @IsNumber() price?: number;
  @IsOptional() @IsString() account_id?: string;
}

class RouteExecutionDto {
  @IsString() code!: string;
  @IsString() direction!: string;
  @Type(() => Number) @IsInt() @Min(1) quantity!: number;
  @IsOptional() @Type(() => Number) @IsNumber() price?: number;
  @IsOptional() @IsString() urgency?: string;
  @IsOptional() @IsString() order_type?: string;
  @IsOptional() @Type(() => Number) @IsNumber() stop_price?: number;
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @IsString() artifact_id?: string;
  @IsOptional() @IsString() output_artifact_id?: string;
  @IsOptional() @IsString() idempotency_key?: string;
}

class OrderEventsQueryDto {
  @IsOptional() @IsString() order_id?: string;
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) limit?: number;
}

class PerformanceQueryDto {
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(0) days?: number;
}

type Req_ = { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } };

function traceId(req: Req_): string {
  return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
}

function userId(req: Req_): string {
  return req.user?.id || 'default';
}

function requestIdempotencyKey(
  req: Req_,
  body?: { idempotency_key?: string },
): string | undefined {
  const headerValue = req.headers?.['idempotency-key'];
  const key = String(body?.idempotency_key ?? headerValue ?? '').trim();
  return key.length > 0 ? key : undefined;
}

@Controller('paper-trading')
export class PaperTradingController {
  constructor(private readonly svc: PaperTradingService) { }

  @Get('accounts')
  async listAccounts(@Req() req: Req_) {
    const data = await this.svc.listAccounts(userId(req));
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('summary')
  async summary(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.summary(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('positions')
  async positions(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.positions(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('orders')
  async orders(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.orders(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('order-events')
  async orderEvents(@Query() query: OrderEventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.orderEvents(userId(req), query);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('pending-orders')
  async pendingOrders(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.pendingOrders(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('order')
  @Throttle({ default: { ttl: 1000, limit: 10 } })
  async placeOrder(@Body() body: PlaceOrderDto, @Req() req: Req_) {
    const data = await this.svc.placeOrder(userId(req), body, requestIdempotencyKey(req, body));
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('cancel')
  async cancelOrder(@Body() body: CancelOrderDto, @Req() req: Req_) {
    const data = await this.svc.cancelOrder(
      userId(req),
      body.order_id,
      requestIdempotencyKey(req, body),
    );
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('update-prices')
  async updatePrices(@Body() body: UpdatePricesDto, @Req() req: Req_) {
    const data = await this.svc.updatePrices(userId(req), body.account_id);
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('reconcile')
  async reconcile(@Body() body: ReconcileDto, @Req() req: Req_) {
    const data = await this.svc.reconcile(userId(req), body);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('nav-history')
  async navHistory(
    @Query('account_id') accountId: string,
    @Query('limit') limit: string,
    @Req() req: Req_,
  ) {
    const data = await this.svc.navHistory(userId(req), accountId, limit ? Number(limit) : undefined);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('performance')
  async performance(@Query() query: PerformanceQueryDto, @Req() req: Req_) {
    const data = await this.svc.performance(userId(req), query.account_id, query.days ?? 30);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('matching-status')
  async matchingStatus(@Req() req: Req_) {
    const data = await this.svc.matchingStatus();
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('nav-status')
  async navStatus(@Req() req: Req_) {
    const data = await this.svc.navStatus();
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('risk-rules')
  async setRiskRules(@Body() body: RiskRulesDto, @Req() req: Req_) {
    const data = await this.svc.setRiskRules(userId(req), body);
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('check-compliance')
  async checkCompliance(@Body() body: ComplianceCheckDto, @Req() req: Req_) {
    const data = await this.svc.checkCompliance(userId(req), body);
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('route-execution')
  async routeExecution(@Body() body: RouteExecutionDto, @Req() req: Req_) {
    const data = await this.svc.routeExecution(
      userId(req),
      body,
      requestIdempotencyKey(req, body),
    );
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('execution-status')
  async executionStatus(@Query('execution_id') executionId: string, @Req() req: Req_) {
    const data = await this.svc.executionStatus(userId(req), executionId);
    return { success: true, data, traceId: traceId(req) };
  }
}
