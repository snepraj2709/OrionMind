import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

vi.mock('./use-auth', () => ({
  useAuth: mocks.useAuth,
}));

const authValue: AuthContextValue = {
  user: null,
  isAuthenticated: false,
  isInitialized: false,
  isPending: false,
  signIn: vi.fn(),
  signUp: vi.fn(),
  signOut: vi.fn(),
  updateUser: vi.fn(),
};

beforeEach(() => {
  mocks.useAuth.mockReturnValue(authValue);
});

describe('client route guards', () => {
  it('withholds protected content until session initialization completes', () => {
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

  it('redirects an initialized unauthenticated protected route to login', async () => {
    mocks.useAuth.mockReturnValue({ ...authValue, isInitialized: true });

    render(
      <ProtectedRoute>
        <div>Private journal</div>
      </ProtectedRoute>,
    );

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/login'));
    expect(screen.queryByText('Private journal')).not.toBeInTheDocument();
  });

  it('renders protected children after restoring an authenticated user', () => {
    mocks.useAuth.mockReturnValue({
      ...authValue,
      isAuthenticated: true,
      isInitialized: true,
      user: { id: 'user-1', email: 'reader@example.com', name: 'Reader' },
    });

    render(
      <ProtectedRoute>
        <div>Private journal</div>
      </ProtectedRoute>,
    );

    expect(screen.getByText('Private journal')).toBeVisible();
  });

  it('redirects authenticated users away from auth routes', async () => {
    mocks.useAuth.mockReturnValue({
      ...authValue,
      isAuthenticated: true,
      isInitialized: true,
      user: { id: 'user-1', email: 'reader@example.com', name: 'Reader' },
    });

    render(
      <AuthRouteGuard>
        <div>Login form</div>
      </AuthRouteGuard>,
    );

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/entries'));
    expect(screen.queryByText('Login form')).not.toBeInTheDocument();
  });
});
