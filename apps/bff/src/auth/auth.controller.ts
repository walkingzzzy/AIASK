import { Body, Controller, Get, Headers, Post, Req, Res, UnauthorizedException } from '@nestjs/common';
import { Request, Response } from 'express';
import { AuthService } from './auth.service';
import { LoginDto } from './dto/login.dto';
import { RegisterDto } from './dto/register.dto';
import { RefreshDto } from './dto/refresh.dto';
import { LogoutDto } from './dto/logout.dto';
import { Public } from '../rbac/public.decorator';

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  private setCookies(res: Response, accessToken: string, refreshToken: string, accessTtl: number) {
    const isProduction = process.env.NODE_ENV === 'production';
    const commonOpts = { path: '/', sameSite: 'lax' as const, secure: isProduction, httpOnly: true };
    res.cookie('access_token', accessToken, { ...commonOpts, maxAge: accessTtl * 1000 });
    res.cookie('refresh_token', refreshToken, { ...commonOpts, maxAge: 7 * 24 * 60 * 60 * 1000 });
  }

  private clearTokenCookies(res: Response) {
    res.clearCookie('access_token', { path: '/' });
    res.clearCookie('refresh_token', { path: '/' });
  }

  @Public()
  @Post('login')
  async login(@Body() body: LoginDto, @Res({ passthrough: true }) res: Response) {
    const result = await this.authService.login(body.username, body.password);
    this.setCookies(res, result.accessToken, result.refreshToken, result.expiresIn);
    return { user: result.user, expiresIn: result.expiresIn };
  }

  @Public()
  @Post('register')
  async register(@Body() body: RegisterDto, @Res({ passthrough: true }) res: Response) {
    const result = await this.authService.register(body.username, body.password);
    this.setCookies(res, result.accessToken, result.refreshToken, result.expiresIn);
    return { user: result.user, expiresIn: result.expiresIn };
  }

  @Public()
  @Post('refresh')
  async refresh(@Req() req: Request, @Body() body: RefreshDto, @Res({ passthrough: true }) res: Response) {
    const token = req.cookies?.refresh_token || body.refreshToken;
    if (!token) throw new UnauthorizedException('缺少 refresh token');
    const result = await this.authService.refresh(token);
    this.setCookies(res, result.accessToken, result.refreshToken, result.expiresIn);
    return { user: result.user, expiresIn: result.expiresIn };
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
  me(@Req() req: { user?: unknown }) {
    return {
      authenticated: true,
      user: req.user ?? null,
    };
  }

  @Get('profile')
  profile(@Req() req: { user?: any }) {
    const user = req.user ?? {};
    return {
      success: true,
      data: {
        id: user.sub ?? user.id ?? null,
        username: user.username ?? null,
        role: user.role ?? null,
        riskLevel: user.riskLevel ?? 'moderate',
        preferences: user.preferences ?? {},
      },
    };
  }

  @Post('profile')
  async updateProfile(@Req() req: { user?: any }, @Body() body: { riskLevel?: string; preferences?: Record<string, unknown> }) {
    // In-memory mode: just echo back the update (no persistence without DB)
    const user = req.user ?? {};
    return {
      success: true,
      data: {
        id: user.sub ?? user.id ?? null,
        username: user.username ?? null,
        role: user.role ?? null,
        riskLevel: body.riskLevel ?? user.riskLevel ?? 'moderate',
        preferences: body.preferences ?? user.preferences ?? {},
      },
    };
  }

  private extractBearer(authorization?: string): string | undefined {
    if (!authorization) return undefined;
    const [scheme, token] = authorization.split(' ');
    if (!scheme || !token || scheme.toLowerCase() !== 'bearer') return undefined;
    return token;
  }
}

