import { Type } from 'class-transformer';
import { IsInt, IsNotEmpty, IsObject, IsOptional, IsString, Max, Min } from 'class-validator';

export class CreateMcpToolJobDto {
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
  @IsString()
  @IsNotEmpty()
  idempotency_key?: string;
}
