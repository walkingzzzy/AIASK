import { Body, Controller, Get, Param, Post, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import { IsBoolean, IsNumber, IsOptional, IsString, Min } from 'class-validator';
import { ExecutionService } from './execution.service';

class ExecutionWorkbenchQueryDto {
  @IsOptional()
  @IsString()
  executionId?: string;

  @IsOptional()
  @IsString()
  execution_id?: string;

  @IsOptional()
  @IsString()
  accountId?: string;

  @IsOptional()
  @IsString()
  account_id?: string;
}

class ExecutionTasksQueryDto {
  @IsOptional()
  @IsString()
  status?: string;

  @IsOptional()
  @IsString()
  accountId?: string;

  @IsOptional()
  @IsString()
  account_id?: string;
}

class LiveOrdersQueryDto {
  @IsOptional()
  @IsString()
  status?: string;

  @IsOptional()
  @Type(() => Number)
  @Min(1)
  limit?: number;

  @IsOptional()
  @IsString()
  symbols?: string;
}

class LiveOrderEventsQueryDto {
  @IsOptional()
  @Type(() => Number)
  @Min(1)
  limit?: number;
}

class LiveFillsQueryDto {
  @IsOptional()
  @IsString()
  order_id?: string;

  @IsOptional()
  @Type(() => Number)
  @Min(1)
  limit?: number;

  @IsOptional()
  @IsString()
  symbols?: string;
}

class LiveSubmitOrderDto {
  @IsOptional()
  @IsString()
  symbol?: string;

  @IsOptional()
  @IsString()
  code?: string;

  @IsOptional()
  @IsString()
  side?: string;

  @IsOptional()
  @IsString()
  direction?: string;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  qty?: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  quantity?: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  notional?: number;

  @IsOptional()
  @IsString()
  type?: string;

  @IsOptional()
  @IsString()
  order_type?: string;

  @IsOptional()
  @IsString()
  time_in_force?: string;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  limit_price?: number;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  stop_price?: number;

  @IsOptional()
  @IsString()
  client_order_id?: string;

  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  extended_hours?: boolean;

  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  dry_run?: boolean;
}

class LiveCancelOrderDto {
  @IsString()
  order_id!: string;

  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  dry_run?: boolean;
}

class LiveMirrorToPaperDto {
  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  execute?: boolean;

  @IsOptional()
  @IsString()
  paper_account_id?: string;

  @IsOptional()
  @IsString()
  paper_account_name?: string;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(0)
  initial_capital?: number;
}

class LiveSyncOrderEventsDto {
  @IsString()
  order_id!: string;

  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(1)
  limit?: number;

  @IsOptional()
  @Type(() => Boolean)
  @IsBoolean()
  persist_artifact?: boolean;

  @IsOptional()
  @IsString()
  output_artifact_id?: string;
}

type RequestWithUser = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
  user?: { id?: string; sub?: string };
};

@Controller('execution')
export class ExecutionController {
  constructor(private readonly executionService: ExecutionService) {}

  private userId(req: RequestWithUser) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  private traceId(req: RequestWithUser) {
    return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
  }

  @Get('workbench')
  async workbench(@Query() query: ExecutionWorkbenchQueryDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.workbench(
      this.userId(req),
      query.executionId ?? query.execution_id,
      query.accountId ?? query.account_id,
    );
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('tasks')
  async tasks(@Query() query: ExecutionTasksQueryDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.tasks(this.userId(req), query.status);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('tasks/:taskId')
  async taskDetail(
    @Param('taskId') taskId: string,
    @Query() query: ExecutionTasksQueryDto,
    @Req() req: RequestWithUser,
  ) {
    const data = await this.executionService.taskDetail(
      this.userId(req),
      taskId,
      query.accountId ?? query.account_id,
    );
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('artifact/:artifactId')
  async artifact(
    @Param('artifactId') artifactId: string,
    @Query() query: ExecutionTasksQueryDto,
    @Req() req: RequestWithUser,
  ) {
    const data = await this.executionService.artifact(
      this.userId(req),
      artifactId,
      query.accountId ?? query.account_id,
    );
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('artifacts')
  async artifacts(@Query() query: ExecutionTasksQueryDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.listArtifacts(
      this.userId(req),
      query.accountId ?? query.account_id,
    );
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/gateway-status')
  async liveGatewayStatus(@Req() req: RequestWithUser) {
    const data = await this.executionService.liveGatewayStatus();
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/account')
  async liveAccount(@Req() req: RequestWithUser) {
    const data = await this.executionService.liveAccount();
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/positions')
  async livePositions(@Req() req: RequestWithUser) {
    const data = await this.executionService.livePositions();
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/orders')
  async liveOrders(@Query() query: LiveOrdersQueryDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveOrders({
      status: query.status,
      limit: query.limit,
      symbols: query.symbols,
    });
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/orders/:orderId')
  async liveOrderStatus(@Param('orderId') orderId: string, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveOrderStatus(orderId);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/orders/:orderId/events')
  async liveOrderEvents(
    @Param('orderId') orderId: string,
    @Query() query: LiveOrderEventsQueryDto,
    @Req() req: RequestWithUser,
  ) {
    const data = await this.executionService.liveOrderEvents(orderId, { limit: query.limit });
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/fills')
  async liveFills(@Query() query: LiveFillsQueryDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveFills({
      order_id: query.order_id,
      limit: query.limit,
      symbols: query.symbols,
    });
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('live/orders/:orderId/receipt')
  async liveBrokerReceipt(@Param('orderId') orderId: string, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveBrokerReceipt(orderId);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('live/orders')
  async liveSubmitOrder(@Body() body: LiveSubmitOrderDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveSubmitOrder(body);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('live/orders/cancel')
  async liveCancelOrder(@Body() body: LiveCancelOrderDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveCancelOrder(body);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('live/mirror-to-paper')
  async liveMirrorToPaper(@Body() body: LiveMirrorToPaperDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveMirrorToPaper(this.userId(req), body);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('live/order-events/sync')
  async liveSyncOrderEvents(@Body() body: LiveSyncOrderEventsDto, @Req() req: RequestWithUser) {
    const data = await this.executionService.liveSyncOrderEvents(body);
    return { success: true, data, traceId: this.traceId(req) };
  }
}
