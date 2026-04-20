import {
  CallHandler,
  ExecutionContext,
  HttpException,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { Observable, catchError, tap, throwError } from 'rxjs';
import { ObservabilityService } from './observability.service';

@Injectable()
export class ObservabilityInterceptor implements NestInterceptor {
  constructor(private readonly observability: ObservabilityService) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const startedAt = Date.now();
    const http = context.switchToHttp();
    const request = http.getRequest<{
      method?: string;
      baseUrl?: string;
      route?: { path?: string };
      url?: string;
    }>();
    const response = http.getResponse<{ statusCode?: number }>();
    const route = `${request.baseUrl ?? ''}${request.route?.path ?? request.url ?? 'UNKNOWN'}`;
    const method = request.method ?? 'UNKNOWN';

    const record = (statusCode: number, degraded: boolean) => {
      this.observability.recordHttpRequest({
        method,
        route,
        statusCode,
        durationMs: Date.now() - startedAt,
        degraded,
      });
    };

    return next.handle().pipe(
      tap({
        next: () => {
          record(response.statusCode ?? 200, false);
        },
      }),
      catchError((error: unknown) => {
        const statusCode =
          error instanceof HttpException
            ? error.getStatus()
            : typeof response.statusCode === 'number'
              ? response.statusCode
              : 500;
        const degraded = Boolean(
          error instanceof HttpException
            && typeof error.getResponse() === 'object'
            && error.getResponse() !== null
            && (error.getResponse() as { degraded?: unknown }).degraded,
        );
        record(statusCode, degraded);
        return throwError(() => error);
      }),
    );
  }
}
