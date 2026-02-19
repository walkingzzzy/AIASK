import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
  HttpStatus,
} from '@nestjs/common';

type ErrorBody = {
  success: false;
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
  traceId: string;
  path: string;
  timestamp: string;
};

@Catch()
export class GlobalHttpExceptionFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<{
      status: (code: number) => { json: (body: unknown) => void };
    }>();
    const request = ctx.getRequest<{
      url?: string;
      traceId?: string;
      headers?: Record<string, string | undefined>;
    }>();

    const status = this.resolveStatus(exception);
    const { code, message, detail } = this.resolveErrorMeta(exception, status);
    const traceId =
      request.traceId ||
      request.headers?.['x-trace-id'] ||
      request.headers?.['x-request-id'] ||
      `trace_${Math.random().toString(36).slice(2, 10)}`;

    const body: ErrorBody = {
      success: false,
      error: {
        code,
        message,
        ...(detail !== undefined ? { detail } : {}),
      },
      traceId: String(traceId),
      path: request.url ?? 'UNKNOWN',
      timestamp: new Date().toISOString(),
    };

    response.status(status).json(body);
  }

  private resolveStatus(exception: unknown): number {
    if (exception instanceof HttpException) {
      return exception.getStatus();
    }
    return HttpStatus.INTERNAL_SERVER_ERROR;
  }

  private resolveErrorMeta(exception: unknown, status: number) {
    if (exception instanceof HttpException) {
      const payload = exception.getResponse();
      if (typeof payload === 'string') {
        return {
          code: `HTTP_${status}`,
          message: payload,
        };
      }
      if (payload && typeof payload === 'object') {
        const body = payload as Record<string, unknown>;
        const message =
          typeof body.message === 'string'
            ? body.message
            : Array.isArray(body.message)
              ? body.message.join('; ')
              : `HTTP ${status}`;
        const code =
          typeof body.code === 'string'
            ? body.code
            : typeof body.error === 'string'
              ? body.error
              : `HTTP_${status}`;
        const detail = body.detail;
        return { code, message, ...(detail !== undefined ? { detail } : {}) };
      }
    }

    return {
      code: 'INTERNAL_ERROR',
      message: exception instanceof Error ? exception.message : '服务内部错误',
    };
  }
}

