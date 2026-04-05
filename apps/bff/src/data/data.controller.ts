import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import { IsArray, IsBoolean, IsInt, IsNumber, IsObject, IsOptional, IsString, Matches, Min } from 'class-validator';
import { DataService } from './data.service';

class OptionChainDto {
  @IsString() underlying!: string;
  @IsOptional() @IsString() expiryMonth?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) limit?: number;
}

class TradingDatesDto {
  @IsOptional() @IsString() startDate?: string;
  @IsOptional() @IsString() endDate?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) count?: number;
}

class IpoDto {
  @IsOptional() @IsString() ipoType?: string;
  @IsOptional() @IsBoolean() includeFuture?: boolean;
}

class CbDto {
  @IsString() code!: string;
}

class StockCapitalDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsArray() dates?: string[];
}

class PredictionDiagnosisDto {
  @IsArray() probabilities!: number[];
  @IsArray() labels!: number[];
  @IsOptional() @IsArray() rawScores?: number[];
  @IsOptional() @IsString() method?: string;
  @IsOptional() @Type(() => Number) @IsNumber() plattA?: number;
  @IsOptional() @Type(() => Number) @IsNumber() plattB?: number;
  @IsOptional() @Type(() => Number) @IsNumber() coverageTarget?: number;
  @IsOptional() @IsString() datasetId?: string;
  @IsOptional() @IsString() runId?: string;
  @IsOptional() @Type(() => Boolean) @IsBoolean() persistArtifact?: boolean;
  @IsOptional() @IsString() outputArtifactId?: string;
  @IsOptional() @IsString() asOf?: string;
}

class DataQualityWorkflowDto {
  @IsOptional() @IsString() datasetId?: string;
  @IsOptional() @IsArray() @IsObject({ each: true }) records?: Array<Record<string, unknown>>;
  @IsOptional() @IsArray() @IsString({ each: true }) requiredFields?: string[];
  @IsOptional() @IsString() asOfField?: string;
  @IsOptional() @IsString() asOfValue?: string;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) sourceChain?: string[];
  @IsOptional() @Type(() => Number) @IsNumber() minimumQualityThreshold?: number;
  @IsOptional() @Type(() => Boolean) @IsBoolean() persistArtifact?: boolean;
  @IsOptional() @IsString() outputArtifactId?: string;
  @IsOptional() @IsString() asOf?: string;
}

class WorkflowGuideDto {
  @IsString() name!: string;
}

class RunSnapshotDto {
  @IsString() runId!: string;
}

class DatasetResourceDto {
  @IsString() datasetId!: string;
}

class FactorProfileDto {
  @IsString() factorId!: string;
}

class ModelProfileDto {
  @IsString() modelId!: string;
}

class StrategyGovernanceDto {
  @IsString() strategyId!: string;
}

class ExperimentSummaryDto {
  @IsString() experimentId!: string;
}

@Controller('data')
export class DataController {
  constructor(private readonly dataService: DataService) {}

  @Get('option-chain')
  async optionChain(@Query() query: OptionChainDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getOptionChain(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('trading-dates')
  async tradingDates(@Query() query: TradingDatesDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getTradingDates(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('ipo')
  async ipo(@Query() query: IpoDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getIpoInfo(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('cb')
  async cb(@Query() query: CbDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getCbInfo(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('capital')
  async capital(@Query() query: StockCapitalDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getStockCapital(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('prediction-diagnosis')
  async predictionDiagnosis(
    @Body() body: PredictionDiagnosisDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.dataService.predictionDiagnosisWorkflow(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('quality-workflow')
  async qualityWorkflow(
    @Body() body: DataQualityWorkflowDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.dataService.dataQualityWorkflow(body);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('tool-catalog')
  async toolCatalog(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getToolCatalog();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('workflow-guide')
  async workflowGuide(@Query() query: WorkflowGuideDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getWorkflowGuide(query.name);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('run-snapshot')
  async runSnapshot(@Query() query: RunSnapshotDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getRunSnapshot(query.runId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('dataset-quality')
  async datasetQuality(@Query() query: DatasetResourceDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getDatasetQuality(query.datasetId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('dataset-profile')
  async datasetProfile(@Query() query: DatasetResourceDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getDatasetProfile(query.datasetId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('factor-profile')
  async factorProfile(@Query() query: FactorProfileDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getFactorProfile(query.factorId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('model-profile')
  async modelProfile(@Query() query: ModelProfileDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getModelProfile(query.modelId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('strategy-governance')
  async strategyGovernance(@Query() query: StrategyGovernanceDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getStrategyGovernance(query.strategyId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('experiment-summary')
  async experimentSummary(@Query() query: ExperimentSummaryDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getExperimentSummary(query.experimentId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('governance-report')
  async governanceReport(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.dataService.getSystemGovernanceReport();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
