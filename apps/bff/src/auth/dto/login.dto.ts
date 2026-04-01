import { IsOptional, IsString, Matches, MinLength } from 'class-validator';

export class LoginDto {
  @IsString()
  username!: string;

  @IsString()
  @MinLength(3)
  password!: string;

  @IsOptional()
  @IsString()
  @Matches(/^(\d{6}|[A-Za-z0-9]{8})$/, { message: '2FA 验证码必须为 6 位动态码或 8 位恢复码' })
  otpCode?: string;
}
