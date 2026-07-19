import type { AppError } from '@/lib/errors/app-error';

export type ViewState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: AppError }
  | { status: 'empty' }
  | { status: 'insufficient'; reason: string }
  | { status: 'success'; data: T };
