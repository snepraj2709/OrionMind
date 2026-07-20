import { resolveApiUrl } from '@/config/api';

export type ApiRequest = (
  path: string,
  init?: RequestInit,
) => Promise<Response>;

export const apiRequest: ApiRequest = (path, init) =>
  fetch(resolveApiUrl(path), {
    ...init,
    credentials: 'include',
  });
