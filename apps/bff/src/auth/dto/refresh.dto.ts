import { IsOptional, IsString, MinLength } from 'class-validator';

export class RefreshDto {
  @IsOptional()
  @IsString()
  @MinLength(10)
  refreshToken?: string;
}

