import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { AuthService } from '../auth/auth.service';
import { IS_PUBLIC_KEY } from './public.decorator';

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private readonly reflector: Reflector,
    private readonly authService: AuthService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<{ headers: Record<string, string>; cookies?: Record<string, string>; user?: unknown }>();
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    const authorization = request.headers?.authorization;
    const token = this.extractBearer(authorization) || request.cookies?.access_token;

    if (!token) {
      if (isPublic) return true;
      throw new UnauthorizedException('缺少 Bearer token');
    }

    try {
      request.user = await this.authService.verifyAccessToken(token);
    } catch (error) {
      if (isPublic) {
        return true;
      }
      throw error;
    }

    return true;
  }

  private extractBearer(authorization?: string): string | undefined {
    if (!authorization) return undefined;
    const [scheme, token] = authorization.split(' ');
    if (!scheme || !token || scheme.toLowerCase() !== 'bearer') return undefined;
    return token;
  }
}
