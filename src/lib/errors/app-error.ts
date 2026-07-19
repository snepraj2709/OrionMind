export type AppErrorCode =
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'payload_too_large'
  | 'rate_limited'
  | 'dependency_unavailable'
  | 'network'
  | 'unknown';

interface AppErrorOptions {
  code?: AppErrorCode;
  status?: number;
  retryable?: boolean;
  cause?: unknown;
}

export class AppError extends Error {
  readonly code: AppErrorCode;
  readonly status?: number;
  readonly retryable: boolean;

  constructor(message: string, options: AppErrorOptions = {}) {
    super(message, { cause: options.cause });
    this.name = 'AppError';
    this.code = options.code ?? 'unknown';
    this.status = options.status;
    this.retryable = options.retryable ?? false;
  }
}

export function normalizeError(error: unknown): AppError {
  if (error instanceof AppError) {
    return error;
  }

  if (error instanceof Error) {
    return new AppError('An unexpected error occurred.', { cause: error });
  }

  return new AppError('An unexpected error occurred.');
}
