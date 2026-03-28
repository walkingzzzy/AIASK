import { BadRequestException, Body, Controller, Get, Headers, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import { IsString, Length, Matches } from 'class-validator';
import { Request, Response } from 'express';
import { AuthService } from './auth.service';
import { PreferencesService } from './preferences.service';
import { TotpService } from './totp.service';
import { ChangePasswordDto } from './dto/change-password.dto';
import { LoginDto } from './dto/login.dto';
import { RegisterDto } from './dto/register.dto';
import { RefreshDto } from './dto/refresh.dto';
import { LogoutDto } from './dto/logout.dto';
import { Public } from '../rbac/public.decorator';

class RevokeSessionDto {
  sessionId!: string;
}

class Verify2faDto {
  @IsString()
  @Length(6, 6, { message: '验证码必须为 6 位数字' })
  @Matches(/^\d{6}$/, { message: '验证码必须为 6 位数字' })
  code!: string;
}

@Controller('auth')
export class AuthController {
  constructor(
    private readonly authService: AuthService,
    private readonly preferencesService: PreferencesService,
    private readonly totpService: TotpService,
  ) {}

  private shouldUseSecureCookies(req: Request) {
    const forced = String(process.env.APP_COOKIE_SECURE ?? '').trim().toLowerCase();
    if (['1', 'true', 'yes', 'on'].includes(forced)) return true;
    if (['0', 'false', 'no', 'off'].includes(forced)) return false;
    if (process.env.NODE_ENV !== 'production') return false;

    const hostname = String(req.hostname || req.headers.host || '')
      .split(':')[0]
      .trim()
      .toLowerCase();

    return !['localhost', '127.0.0.1', '::1'].includes(hostname);
  }

  private setCookies(req: Request, res: Response, accessToken: string, refreshToken: string, accessTtl: number) {
    const commonOpts = {
      path: '/',
      sameSite: 'lax' as const,
      secure: this.shouldUseSecureCookies(req),
      httpOnly: true,
    };
    res.cookie('access_token', accessToken, { ...commonOpts, maxAge: accessTtl * 1000 });
    res.cookie('refresh_token', refreshToken, { ...commonOpts, maxAge: 7 * 24 * 60 * 60 * 1000 });
  }

  private clearTokenCookies(res: Response) {
    res.clearCookie('access_token', { path: '/' });
    res.clearCookie('refresh_token', { path: '/' });
  }

  @Public()
  @Post('login')
  async login(@Req() req: Request, @Body() body: LoginDto, @Res({ passthrough: true }) res: Response) {
    const result = await this.authService.login(body.username, body.password);
    this.setCookies(req, res, result.accessToken, result.refreshToken, result.expiresIn);
    return { success: true, data: { user: result.user, expiresIn: result.expiresIn, tokenDelivery: 'cookie' } };
  }

  @Public()
  @Post('register')
  async register(@Req() req: Request, @Body() body: RegisterDto, @Res({ passthrough: true }) res: Response) {
    const result = await this.authService.register(body.username, body.password);
    this.setCookies(req, res, result.accessToken, result.refreshToken, result.expiresIn);
    return { success: true, data: { user: result.user, expiresIn: result.expiresIn, tokenDelivery: 'cookie' } };
  }

  @Public()
  @Post('refresh')
  async refresh(@Req() req: Request, @Body() body: RefreshDto, @Res({ passthrough: true }) res: Response) {
    const token = req.cookies?.refresh_token || body.refreshToken;
    if (!token) throw new UnauthorizedException('缺少 refresh token');
    const result = await this.authService.refresh(token);
    this.setCookies(req, res, result.accessToken, result.refreshToken, result.expiresIn);
    return { success: true, data: { user: result.user, expiresIn: result.expiresIn, tokenDelivery: 'cookie' } };
  }

  @Post('logout')
  async logout(@Req() req: Request, @Body() body: LogoutDto, @Headers('authorization') authorization: string | undefined, @Res({ passthrough: true }) res: Response) {
    const accessToken = this.extractBearer(authorization) || req.cookies?.access_token;
    const refreshToken = req.cookies?.refresh_token || body.refreshToken;
    await this.authService.logout({ accessToken, refreshToken });
    this.clearTokenCookies(res);
    return { success: true };
  }

  @Get('me')
  async me(@Req() req: { user?: { id?: string; sub?: string } }) {
    const userId = this.currentUserId(req);
    return {
      authenticated: true,
      user: await this.authService.getProfile(userId),
    };
  }

  @Get('profile')
  async profile(@Req() req: { user?: { id?: string; sub?: string } }) {
    const userId = this.currentUserId(req);
    return {
      success: true,
      data: await this.authService.getProfile(userId),
    };
  }

  @Post('profile')
  async updateProfile(
    @Req() req: { user?: { id?: string; sub?: string } },
    @Body() body: { riskLevel?: string; nickname?: string; avatarUrl?: string; preferences?: Record<string, unknown> },
  ) {
    const userId = this.currentUserId(req);
    return {
      success: true,
      data: await this.authService.updateProfile(userId, body),
    };
  }

  @Post('change-password')
  async changePassword(@Req() req: { user?: { id?: string; sub?: string } }, @Body() body: ChangePasswordDto) {
    const userId = this.currentUserId(req);
    return this.authService.changePassword(userId, body.oldPassword, body.newPassword);
  }

  @Get('sessions')
  async sessions(@Req() req: { user?: { id?: string; sub?: string; jti?: string } }) {
    const userId = this.currentUserId(req);
    return {
      success: true,
      data: {
        items: await this.authService.listSessions(userId, req.user?.jti),
      },
    };
  }

  @Post('sessions/revoke')
  async revokeSession(@Req() req: { user?: { id?: string; sub?: string; jti?: string } }, @Body() body: RevokeSessionDto) {
    const userId = this.currentUserId(req);
    return this.authService.revokeSession(userId, body.sessionId, req.user?.jti);
  }

  @Get('2fa/status')
  async get2faStatus(@Req() req: { user?: { id?: string; sub?: string } }) {
    const userId = this.currentUserId(req);
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const enabled = !!(prefs as { totpEnabled?: boolean }).totpEnabled;
    return { data: { enabled } };
  }

  @Post('2fa/setup')
  async setup2fa(@Req() req: { user?: { id?: string; sub?: string } }) {
    const userId = this.currentUserId(req);
    const profile = await this.authService.getProfile(userId);
    const accountName = (profile as { username?: string }).username ?? userId;
    const secret = this.totpService.generateSecret();
    const uri = this.totpService.generateUri(secret, accountName);
    const backupCodes = this.totpService.generateBackupCodes();
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const updated = {
      ...prefs,
      totpSecret: secret,
      totpBackupCodes: backupCodes,
    };
    await this.preferencesService.setUserPreferences(userId, updated);
    return { data: { secret, uri, backupCodes } };
  }

  @Post('2fa/verify')
  async verify2fa(@Req() req: { user?: { id?: string; sub?: string } }, @Body() body: Verify2faDto) {
    const userId = this.currentUserId(req);
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const secret = (prefs as { totpSecret?: string }).totpSecret;
    if (!secret) throw new BadRequestException('请先完成 2FA 设置');
    if (!this.totpService.verify(body.code, secret)) {
      throw new BadRequestException('验证码无效');
    }
    const updated = { ...prefs, totpEnabled: true };
    await this.preferencesService.setUserPreferences(userId, updated);
    return { success: true };
  }

  @Post('2fa/disable')
  async disable2fa(@Req() req: { user?: { id?: string; sub?: string } }) {
    const userId = this.currentUserId(req);
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const rest = { ...(prefs as Record<string, unknown>) };
    delete rest.totpSecret;
    delete rest.totpEnabled;
    delete rest.totpBackupCodes;
    await this.preferencesService.setUserPreferences(userId, rest);
    return { success: true };
  }

  private extractBearer(authorization?: string): string | undefined {
    const { extractBearer } = require('./extract-bearer');
    return extractBearer(authorization);
  }

  private currentUserId(req: { user?: { id?: string; sub?: string } }) {
    const userId = req.user?.sub ?? req.user?.id;
    if (!userId) throw new UnauthorizedException('缺少用户身份');
    return userId;
  }
}
