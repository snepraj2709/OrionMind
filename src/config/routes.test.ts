import { describe, expect, it } from 'vitest';

import {
  createLoginRedirect,
  entryDetailPath,
  findRouteByPathname,
  getActiveSidebarRoute,
  isProtectedPath,
  pathWithReturnTo,
  resolvePostAuthPath,
  routes,
  safeRedirectPath,
} from './routes';

describe('route registry', () => {
  it('contains unique paths and the exact public auth boundary', () => {
    const paths = Object.values(routes).map((route) => route.path);
    expect(new Set(paths).size).toBe(paths.length);
    expect(
      Object.values(routes)
        .filter((route) => route.authentication !== 'required')
        .map((route) => route.path),
    ).toEqual(['/', '/login', '/signup', '/dev/design-system']);
    expect(paths).not.toContain('/forgot-password');
  });

  it('matches protected dynamic routes to their navigation parent', () => {
    expect(findRouteByPathname('/entries/entry-123')?.[0]).toBe('entryDetail');
    expect(isProtectedPath('/entries/entry-123')).toBe(true);
    expect(getActiveSidebarRoute('/entries/entry-123')).toBe('entries');
  });

  it('does not register retired product routes', () => {
    expect(findRouteByPathname('/ideas')).toBeUndefined();
    expect(findRouteByPathname('/memories')).toBeUndefined();
  });

  it('builds encoded entry detail paths', () => {
    expect(entryDetailPath('entry / 123')).toBe('/entries/entry%20%2F%20123');
  });
});

describe('returnTo sanitization', () => {
  it.each([
    ['/entries?page=2&page_size=10', '/entries?page=2&page_size=10'],
    ['/entries?access_token=secret&search=focus', '/entries?search=focus'],
    ['/reflections?range=30d&unknown=value', '/reflections?range=30d'],
    ['/journey?range=all', '/journey?range=all'],
  ])(
    'keeps known protected routes and only allowlisted query keys',
    (value, expected) => {
      expect(safeRedirectPath(value)).toBe(expected);
    },
  );

  it.each([
    'https://example.com',
    '//example.com',
    '%2F%2Fexample.com',
    'entries',
    '/login?returnTo=/entries',
    '/signup',
    '/unknown',
    '/entries#access_token=secret',
    '/entries\\evil',
    '/entries%5Cevil',
    '/entries?search=line%0Abreak',
    undefined,
  ])('rejects unsafe, public, or unknown destination %s', (destination) => {
    expect(safeRedirectPath(destination)).toBe(routes.entries.path);
  });

  it('preserves a safe destination while moving to login', () => {
    expect(pathWithReturnTo(routes.login.path, '/entries/new')).toBe(
      '/login?returnTo=%2Fentries%2Fnew',
    );
    expect(pathWithReturnTo(routes.login.path, '//example.com')).toBe('/login');
    expect(createLoginRedirect('/entries', '?page=2')).toBe(
      '/login?returnTo=%2Fentries%3Fpage%3D2',
    );
  });

  it('defaults unsafe post-auth destinations to entries', () => {
    expect(resolvePostAuthPath('https://example.com')).toBe('/entries');
  });
});
