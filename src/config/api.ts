function normalizeApiBaseUrl(value: string | undefined) {
  return value?.trim().replace(/\/+$/, '') ?? '';
}

export function publicFeatureEnabled(value: string | undefined) {
  return value?.trim().toLowerCase() === 'true';
}

export const apiConfig = Object.freeze({
  baseUrl: normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL),
  reflectionsEnabled: publicFeatureEnabled(
    process.env.NEXT_PUBLIC_REFLECTIONS_ENABLED,
  ),
});

export function resolveApiUrl(path: string) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${apiConfig.baseUrl}${normalizedPath}`;
}
