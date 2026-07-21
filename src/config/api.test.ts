import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('API configuration', () => {
  it('uses same-origin paths when no backend base URL is configured', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '');
    const { apiConfig, resolveApiUrl } = await import('./api');

    expect(apiConfig.baseUrl).toBe('');
    expect(resolveApiUrl('/api/v1/reflection')).toBe('/api/v1/reflection');
  });

  it('reads and normalizes the backend base URL from the environment', async () => {
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', ' https://api.orion.test/ ');
    const { apiConfig, resolveApiUrl } = await import('./api');

    expect(apiConfig.baseUrl).toBe('https://api.orion.test');
    expect(resolveApiUrl('/api/v1/reflection')).toBe(
      'https://api.orion.test/api/v1/reflection',
    );
  });

  it('keeps Reflections disabled when its public flag is absent', async () => {
    vi.stubEnv('NEXT_PUBLIC_REFLECTIONS_ENABLED', '');
    const { apiConfig } = await import('./api');

    expect(apiConfig.reflectionsEnabled).toBe(false);
  });

  it('enables Reflections only for an explicit true public flag', async () => {
    vi.stubEnv('NEXT_PUBLIC_REFLECTIONS_ENABLED', 'true');
    const { apiConfig, publicFeatureEnabled } = await import('./api');

    expect(apiConfig.reflectionsEnabled).toBe(true);
    expect(publicFeatureEnabled('false')).toBe(false);
    expect(publicFeatureEnabled('unexpected')).toBe(false);
  });
});
