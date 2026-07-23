import {
  BookOpenText,
  CheckCircle2,
  FileText,
  Home,
  LogIn,
  type LucideIcon,
  Palette,
  PenLine,
  Sparkles,
  UserPlus,
  UserRound,
  Waypoints,
} from 'lucide-react';
import type { Route } from 'next';

export type RouteVisibility = 'authenticated' | 'public';
export type AuthenticationRequirement =
  'anonymous-only' | 'optional' | 'required';
export type RouteKey =
  | 'home'
  | 'login'
  | 'signup'
  | 'entries'
  | 'newEntry'
  | 'entryDetail'
  | 'review'
  | 'legacyApprovals'
  | 'reflections'
  | 'journey'
  | 'profile'
  | 'designSystem';

export interface RouteDefinition {
  path: string;
  label: string;
  visibility: RouteVisibility;
  authentication: AuthenticationRequirement;
  showInSidebar: boolean;
  icon: LucideIcon;
  safeQueryKeys: readonly string[];
  navigationParent?: RouteKey;
}

export const routes = {
  home: {
    path: '/',
    label: 'Orion',
    visibility: 'public',
    authentication: 'optional',
    showInSidebar: false,
    icon: Home,
    safeQueryKeys: [],
  },
  login: {
    path: '/login',
    label: 'Log in',
    visibility: 'public',
    authentication: 'anonymous-only',
    showInSidebar: false,
    icon: LogIn,
    safeQueryKeys: ['returnTo', 'state', 'mode'],
  },
  signup: {
    path: '/signup',
    label: 'Sign up',
    visibility: 'public',
    authentication: 'anonymous-only',
    showInSidebar: false,
    icon: UserPlus,
    safeQueryKeys: ['state'],
  },
  entries: {
    path: '/entries',
    label: 'Entries',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: BookOpenText,
    safeQueryKeys: ['page', 'page_size', 'search', 'processing_status'],
  },
  newEntry: {
    path: '/entries/new',
    label: 'New Entry',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: PenLine,
    safeQueryKeys: [],
  },
  entryDetail: {
    path: '/entries/[entryId]',
    label: 'Entry',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: false,
    icon: FileText,
    safeQueryKeys: [],
    navigationParent: 'entries',
  },
  review: {
    path: '/review',
    label: 'Review',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: CheckCircle2,
    safeQueryKeys: ['scope', 'category', 'status', 'page'],
  },
  legacyApprovals: {
    path: '/approvals',
    label: 'Review',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: false,
    icon: CheckCircle2,
    safeQueryKeys: [],
    navigationParent: 'review',
  },
  reflections: {
    path: '/reflections',
    label: 'Reflections',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: Sparkles,
    safeQueryKeys: ['type', 'range'],
  },
  journey: {
    path: '/journey',
    label: 'Journey',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: Waypoints,
    safeQueryKeys: ['range'],
  },
  profile: {
    path: '/profile',
    label: 'Profile',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: UserRound,
    safeQueryKeys: [],
  },
  designSystem: {
    path: '/dev/design-system',
    label: 'Design system',
    visibility: 'public',
    authentication: 'optional',
    showInSidebar: false,
    icon: Palette,
    safeQueryKeys: [],
  },
} as const satisfies Record<RouteKey, RouteDefinition>;

export type AppRoute = (typeof routes)[RouteKey];
export type SidebarRoute = Extract<AppRoute, { showInSidebar: true }> & {
  key: RouteKey;
};

export const sidebarRoutes = Object.entries(routes)
  .filter(([, route]) => route.showInSidebar)
  .map(([key, route]) => ({
    key: key as RouteKey,
    ...route,
  })) as SidebarRoute[];

function routePattern(path: string) {
  if (path === routes.home.path) return /^\/$/;

  const pattern = path
    .split('/')
    .map((segment) => (segment.startsWith('[') ? '[^/]+' : segment))
    .join('/');

  return new RegExp(`^${pattern}/?$`);
}

export function findRouteByPathname(pathname: string) {
  return Object.entries(routes).find(([, route]) =>
    routePattern(route.path).test(pathname),
  ) as [RouteKey, AppRoute] | undefined;
}

export function isProtectedPath(pathname: string) {
  return findRouteByPathname(pathname)?.[1].authentication === 'required';
}

export function getActiveSidebarRoute(pathname: string) {
  const match = findRouteByPathname(pathname);
  if (!match) return undefined;

  const [key, route] = match;
  return 'navigationParent' in route ? route.navigationParent : key;
}

export function entryDetailPath(entryId: string) {
  return routes.entryDetail.path.replace(
    '[entryId]',
    encodeURIComponent(entryId),
  ) as Route;
}

export function safeRedirectPath(
  requestedPath: string | null | undefined,
  fallback: string = routes.entries.path,
) {
  if (
    !requestedPath?.startsWith('/') ||
    requestedPath.startsWith('//') ||
    requestedPath.includes('\\') ||
    [...requestedPath].some((character) => {
      const codePoint = character.codePointAt(0) ?? 0;
      return codePoint < 32 || codePoint === 127;
    })
  ) {
    return fallback;
  }

  try {
    const base = 'https://orion.local';
    const target = new URL(requestedPath, base);
    if (target.origin !== base || target.hash) return fallback;
    const decodedPath = decodeURIComponent(target.pathname);
    if (decodedPath.includes('\\')) return fallback;

    const route = findRouteByPathname(target.pathname)?.[1];
    if (!route || route.authentication !== 'required') return fallback;

    const allowedKeys = new Set<string>(route.safeQueryKeys);
    const safeSearch = new URLSearchParams();
    for (const [key, value] of target.searchParams) {
      const safeValue =
        value.length <= 200 &&
        [...value].every((character) => {
          const codePoint = character.codePointAt(0) ?? 0;
          return codePoint >= 32 && codePoint !== 127;
        });
      if (allowedKeys.has(key) && safeValue && !safeSearch.has(key)) {
        safeSearch.set(key, value);
      }
    }

    const query = safeSearch.toString();
    return `${target.pathname}${query ? `?${query}` : ''}`;
  } catch {
    return fallback;
  }
}

export function pathWithReturnTo(
  path: string,
  requestedPath: string | null | undefined,
) {
  if (!requestedPath) return path;

  const redirectTo = safeRedirectPath(requestedPath, '');
  if (!redirectTo) return path;

  const target = new URL(path, 'https://orion.local');
  target.searchParams.set('returnTo', redirectTo);
  return `${target.pathname}${target.search}`;
}

export function createLoginRedirect(pathname: string, search = '') {
  const returnTo = safeRedirectPath(
    `${pathname}${search}`,
    routes.entries.path,
  );
  return pathWithReturnTo(routes.login.path, returnTo);
}

export function resolvePostAuthPath(requestedPath: string | null | undefined) {
  return safeRedirectPath(requestedPath, routes.entries.path);
}
