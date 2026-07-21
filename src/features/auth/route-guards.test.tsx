import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AuthContextValue } from './auth-provider';
import { AuthRouteGuard } from './auth-route-guard';
import { ProtectedRoute } from './protected-route';

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  useAuth: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock('./use-auth', () => ({ useAuth: mocks.useAuth }));

function authValue(
  overrides: Partial<AuthContextValue> = {},
): AuthContextValue {
  return {
    status: 'resolving',
    session: null,
    user: null,
    flow: 'default',
    isAuthenticated: false,
    isInitialized: false,
    isPending: false,
    isRequiredRecoveryActive: false,
    setFlow: vi.fn(),
    signIn: vi.fn(),
    signUp: vi.fn(),
    requestPasswordReset: vi.fn(),
    updatePassword: vi.fn(),
    signOut: vi.fn(),
    updateUser: vi.fn(),
    apiFetch: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => mocks.useAuth.mockReturnValue(authValue()));
afterEach(() => window.history.replaceState({}, '', '/'));

describe('client route guards', () => {
  it('mounts no protected content while session resolution is pending', () => {
    render(
      <ProtectedRoute>
        <div>Private journal</div>
      </ProtectedRoute>,
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      'Restoring your session',
    );
    expect(screen.queryByText('Private journal')).not.toBeInTheDocument();
  });

  it('redirects anonymous protected navigation with a sanitized returnTo', async () => {
    window.history.replaceState({}, '', '/entries?page=2&access_token=secret');
    mocks.useAuth.mockReturnValue(
      authValue({ status: 'anonymous', isInitialized: true }),
    );

    render(
      <ProtectedRoute>
        <div>Private journal</div>
      </ProtectedRoute>,
    );

    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith(
        '/login?returnTo=%2Fentries%3Fpage%3D2',
      ),
    );
    expect(screen.queryByText('Private journal')).not.toBeInTheDocument();
  });

  it('renders protected children only for authenticated status', () => {
    mocks.useAuth.mockReturnValue(
      authValue({
        status: 'authenticated',
        isAuthenticated: true,
        isInitialized: true,
        user: { id: 'user-1', email: 'reader@example.com', name: 'Reader' },
      }),
    );

    render(
      <ProtectedRoute>
        <div>Private journal</div>
      </ProtectedRoute>,
    );
    expect(screen.getByText('Private journal')).toBeVisible();
  });

  it('redirects authenticated auth routes to safe returnTo or entries', async () => {
    window.history.replaceState(
      {},
      '',
      '/login?returnTo=%2Fjourney%3Frange%3Dall',
    );
    mocks.useAuth.mockReturnValue(
      authValue({
        status: 'authenticated',
        isAuthenticated: true,
        isInitialized: true,
      }),
    );
    const first = render(
      <AuthRouteGuard>
        <div>Login form</div>
      </AuthRouteGuard>,
    );
    await waitFor(() =>
      expect(mocks.replace).toHaveBeenCalledWith('/journey?range=all'),
    );
    expect(screen.queryByText('Login form')).not.toBeInTheDocument();
    first.unmount();

    mocks.replace.mockClear();
    window.history.replaceState(
      {},
      '',
      '/login?returnTo=https%3A%2F%2Fevil.test',
    );
    render(
      <AuthRouteGuard>
        <div>Login form</div>
      </AuthRouteGuard>,
    );
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/entries'));
  });

  it('keeps authenticated required recovery on login', () => {
    mocks.useAuth.mockReturnValue(
      authValue({
        status: 'authenticated',
        flow: 'set_new_password',
        isAuthenticated: true,
        isInitialized: true,
        isRequiredRecoveryActive: true,
      }),
    );

    render(
      <AuthRouteGuard>
        <div>Set password form</div>
      </AuthRouteGuard>,
    );
    expect(screen.getByText('Set password form')).toBeVisible();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('shows a safe configuration screen instead of auth content', () => {
    mocks.useAuth.mockReturnValue(
      authValue({ status: 'unconfigured', isInitialized: true }),
    );
    render(
      <AuthRouteGuard>
        <div>Login form</div>
      </AuthRouteGuard>,
    );

    expect(
      screen.getByRole('heading', { name: 'Supabase setup required' }),
    ).toBeVisible();
    expect(screen.queryByText('Login form')).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent('SUPABASE_SECRET_KEY');
  });
});
