import { IsIn, IsOptional, IsString, Matches } from 'class-validator';

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
}
