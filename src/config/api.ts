function normalizeApiBaseUrl(value: string | undefined) {
  return value?.trim().replace(/\/+$/, '') ?? '';
}

export const apiConfig = Object.freeze({
  baseUrl: normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL),
});

export function resolveApiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${apiConfig.baseUrl}${normalizedPath}`;
}
