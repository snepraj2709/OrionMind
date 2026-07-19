import { describe, expect, it } from 'vitest';

import {
  entryDetailPath,
  findRouteByPathname,
  getActiveSidebarRoute,
  isProtectedPath,
  pathWithRedirect,
  routes,
  safeRedirectPath,
} from './routes';

describe('route registry', () => {
  it('contains unique paths', () => {
    const paths = Object.values(routes).map((route) => route.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('matches protected dynamic routes to their navigation parent', () => {
    expect(findRouteByPathname('/entries/entry-123')?.[0]).toBe('entryDetail');
    expect(isProtectedPath('/entries/entry-123')).toBe(true);
    expect(getActiveSidebarRoute('/entries/entry-123')).toBe('entries');
  });

  it('builds encoded entry detail paths', () => {
    expect(entryDetailPath('entry / 123')).toBe('/entries/entry%20%2F%20123');
  });
});

describe('safeRedirectPath', () => {
  it('keeps internal destinations and query strings', () => {
    expect(safeRedirectPath('/entries/new?mode=text')).toBe(
      '/entries/new?mode=text',
    );
  });

  it.each(['https://example.com', '//example.com', 'entries', undefined])(
    'rejects unsafe destination %s',
    (destination) => {
      expect(safeRedirectPath(destination)).toBe(routes.entries.path);
    },
  );

  it('preserves a safe destination while moving between auth routes', () => {
    expect(pathWithRedirect(routes.signup.path, '/entries/new')).toBe(
      '/signup?redirect=%2Fentries%2Fnew',
    );
    expect(pathWithRedirect(routes.signup.path, '//example.com')).toBe(
      routes.signup.path,
    );
  });
});
