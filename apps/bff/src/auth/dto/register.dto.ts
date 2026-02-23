import { IsString, MinLength, MaxLength, Matches } from 'class-validator';

export class RegisterDto {
  @IsString()
  @MinLength(2, { message: '用户名至少2个字符' })
  @MaxLength(20, { message: '用户名最多20个字符' })
  @Matches(/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/, { message: '用户名只能包含字母、数字、下划线或中文' })
  username!: string;

  @IsString()
  @MinLength(6, { message: '密码至少6个字符' })
  password!: string;
}
