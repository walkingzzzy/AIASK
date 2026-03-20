import { Type } from 'class-transformer';
import { IsBoolean, IsIn, IsInt, IsOptional, IsString, Matches, Max, Min } from 'class-validator';

export class UnifiedDecisionBodyDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsOptional()
  @IsString()
  @IsIn(['aggressive', 'balanced', 'conservative'], {
    message: 'investmentStyle 仅支持 aggressive / balanced / conservative',
  })
  investmentStyle?: 'aggressive' | 'balanced' | 'conservative';

  @Type(() => Boolean)
  @IsOptional()
  @IsBoolean({ message: 'legacyMode 必须为布尔值' })
  legacyMode?: boolean;
}

export class UnifiedDecisionDiffQueryDto {
  @Type(() => Number)
  @IsOptional()
  @IsInt({ message: 'limit 必须为整数' })
  @Min(1, { message: 'limit 最小为 1' })
  @Max(100, { message: 'limit 最大为 100' })
  limit?: number;

  @IsOptional()
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code?: string;

  @IsOptional()
  @IsString()
  @IsIn(['aligned', 'mixed', 'divergent'], {
    message: 'actionAlignment 仅支持 aligned / mixed / divergent',
  })
  actionAlignment?: 'aligned' | 'mixed' | 'divergent';
}
