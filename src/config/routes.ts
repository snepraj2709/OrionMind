import {
  BookOpenText,
  CheckCircle2,
  FileText,
  Home,
  KeyRound,
  Lightbulb,
  LogIn,
  type LucideIcon,
  Palette,
  PenLine,
  Sparkles,
  UserPlus,
  UserRound,
  Waypoints,
} from 'lucide-react';

export type RouteVisibility = 'authenticated' | 'public';
export type AuthenticationRequirement =
  'anonymous-only' | 'optional' | 'required';
export type RouteKey =
  | 'home'
  | 'login'
  | 'signup'
  | 'forgotPassword'
  | 'entries'
  | 'newEntry'
  | 'entryDetail'
  | 'approvals'
  | 'ideas'
  | 'memories'
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
  },
  login: {
    path: '/login',
    label: 'Log in',
    visibility: 'public',
    authentication: 'anonymous-only',
    showInSidebar: false,
    icon: LogIn,
  },
  signup: {
    path: '/signup',
    label: 'Sign up',
    visibility: 'public',
    authentication: 'anonymous-only',
    showInSidebar: false,
    icon: UserPlus,
  },
  forgotPassword: {
    path: '/forgot-password',
    label: 'Forgot password',
    visibility: 'public',
    authentication: 'optional',
    showInSidebar: false,
    icon: KeyRound,
  },
  entries: {
    path: '/entries',
    label: 'Entries',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: BookOpenText,
  },
  newEntry: {
    path: '/entries/new',
    label: 'New Entry',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: PenLine,
  },
  entryDetail: {
    path: '/entries/[entryId]',
    label: 'Entry',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: false,
    icon: FileText,
    navigationParent: 'entries',
  },
  approvals: {
    path: '/approvals',
    label: 'Approvals',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: CheckCircle2,
  },
  ideas: {
    path: '/ideas',
    label: 'Ideas',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: Lightbulb,
  },
  memories: {
    path: '/memories',
    label: 'Memories',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: FileText,
  },
  reflections: {
    path: '/reflections',
    label: 'Reflections',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: Sparkles,
  },
  journey: {
    path: '/journey',
    label: 'Journey',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: Waypoints,
  },
  profile: {
    path: '/profile',
    label: 'Profile',
    visibility: 'authenticated',
    authentication: 'required',
    showInSidebar: true,
    icon: UserRound,
  },
  designSystem: {
    path: '/dev/design-system',
    label: 'Design system',
    visibility: 'public',
    authentication: 'optional',
    showInSidebar: false,
    icon: Palette,
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
  );
}

export function safeRedirectPath(
  requestedPath: string | null | undefined,
  fallback: string = routes.entries.path,
) {
  if (!requestedPath?.startsWith('/') || requestedPath.startsWith('//')) {
    return fallback;
  }

  try {
    const base = 'https://orion.local';
    const target = new URL(requestedPath, base);
    return target.origin === base
      ? `${target.pathname}${target.search}`
      : fallback;
  } catch {
    return fallback;
  }
}

export function pathWithRedirect(
  path: string,
  requestedPath: string | null | undefined,
) {
  if (!requestedPath) return path;

  const redirectTo = safeRedirectPath(requestedPath, '');
  if (!redirectTo) return path;

  const target = new URL(path, 'https://orion.local');
  target.searchParams.set('redirect', redirectTo);
  return `${target.pathname}${target.search}`;
}
