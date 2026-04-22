import type { CreateMcpToolJobInput } from '@aiask/shared-types';
import { Transform, Type } from 'class-transformer';
import {
  IsInt,
  IsNotEmpty,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
  Min,
} from 'class-validator';

export class CreateMcpToolJobDto implements CreateMcpToolJobInput {
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsString()
  @IsNotEmpty()
  tool_name!: string;

  @IsOptional()
  @IsObject()
  arguments?: Record<string, unknown>;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1000)
  @Max(300000)
  timeout_ms?: number;

  @IsOptional()
  @Transform(({ value }) => (typeof value === 'string' ? value.trim() : value))
  @IsString()
  @IsNotEmpty()
  @MaxLength(256)
  idempotency_key?: string;
}

export class GetMcpJobDto {
  @IsUUID()
  jobId!: string;
}
