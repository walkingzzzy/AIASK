import { Body, Controller, Get, Headers, Post, Req } from '@nestjs/common';
import { AuthService } from './auth.service';
import { LoginDto } from './dto/login.dto';
import { RefreshDto } from './dto/refresh.dto';
import { LogoutDto } from './dto/logout.dto';
import { Public } from '../rbac/public.decorator';

@Controller('auth')
export class AuthController {
  constructor(private readonly authService: AuthService) {}

  @Public()
  @Post('login')
  login(@Body() body: LoginDto) {
    return this.authService.login(body.username, body.password);
  }

  @Public()
  @Post('refresh')
  refresh(@Body() body: RefreshDto) {
    return this.authService.refresh(body.refreshToken);
  }

  @Post('logout')
  logout(@Body() body: LogoutDto, @Headers('authorization') authorization?: string) {
    const accessToken = this.extractBearer(authorization);
    return this.authService.logout({ accessToken, refreshToken: body.refreshToken });
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

