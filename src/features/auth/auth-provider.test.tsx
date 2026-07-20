import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from './auth-provider';
import { AuthRouteGuard } from './auth-route-guard';
import { ProtectedRoute } from './protected-route';
import { useAuth } from './use-auth';

const mocks = vi.hoisted(() => {
  const replace = vi.fn();
  return {
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(),
    replace,
    router: { replace },
    signInWithPassword: vi.fn(),
    signOut: vi.fn(),
    signUp: vi.fn(),
    unsubscribe: vi.fn(),
  };
});

vi.mock('next/navigation', () => ({
  useRouter: () => mocks.router,
}));

vi.mock('@/services/supabase', () => ({
  getSupabaseBrowserClient: () => ({
    auth: {
      getSession: mocks.getSession,
      onAuthStateChange: mocks.onAuthStateChange,
      signInWithPassword: mocks.signInWithPassword,
      signOut: mocks.signOut,
      signUp: mocks.signUp,
    },
  }),
}));

const supabaseUser = {
  id: 'user-1',
  email: 'reader@example.com',
  user_metadata: { full_name: 'Ada Reader' },
};

const secondSupabaseUser = {
  id: 'user-2',
  email: 'second@example.com',
  user_metadata: { full_name: 'Second Reader' },
};

type AuthStateChangeHandler = (
  event: string,
  session: { user: typeof supabaseUser } | null,
) => void;

let authStateChangeHandler: AuthStateChangeHandler | undefined;

function AuthHarness() {
  const auth = useAuth();
  const [signupResult, setSignupResult] = useState('');

  return (
    <>
      <output data-testid="initialized">{String(auth.isInitialized)}</output>
      <output data-testid="user-name">{auth.user?.name ?? 'none'}</output>
      <output data-testid="signup-result">{signupResult}</output>
      <button
        onClick={() =>
          void auth.signIn({
            email: 'reader@example.com',
            password: 'secure-password',
          })
        }
        type="button"
      >
        Sign in test
      </button>
      <button
        onClick={() =>
          void auth
            .signUp({
              name: 'Ada Reader',
              email: 'reader@example.com',
              password: 'secure-password',
            })
            .then((result) =>
              setSignupResult(result.ok ? result.email : result.error.message),
            )
        }
        type="button"
      >
        Sign up test
      </button>
      <button onClick={() => void auth.signOut()} type="button">
        Sign out test
      </button>
    </>
  );
}

function renderProvider(queryClient = new QueryClient()) {
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthHarness />
        </AuthProvider>
      </QueryClientProvider>,
    ),
  };
}

function renderAuthRouteProvider(queryClient = new QueryClient()) {
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthRouteGuard>
            <AuthHarness />
          </AuthRouteGuard>
        </AuthProvider>
      </QueryClientProvider>,
    ),
  };
}

function renderProtectedProvider(queryClient = new QueryClient()) {
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ProtectedRoute>
            <AuthHarness />
          </ProtectedRoute>
        </AuthProvider>
      </QueryClientProvider>,
    ),
  };
}

beforeEach(() => {
  mocks.getSession.mockResolvedValue({
    data: { session: null },
    error: null,
  });
  authStateChangeHandler = undefined;
  mocks.onAuthStateChange.mockImplementation((handler) => {
    authStateChangeHandler = handler as AuthStateChangeHandler;
    return { data: { subscription: { unsubscribe: mocks.unsubscribe } } };
  });
  mocks.signInWithPassword.mockResolvedValue({
    data: { user: supabaseUser, session: {} },
    error: null,
  });
  mocks.signUp.mockResolvedValue({ data: { user: supabaseUser }, error: null });
  mocks.signOut.mockResolvedValue({ error: null });
});

describe('AuthProvider', () => {
  it('restores the current session and subscribes to auth changes', async () => {
    mocks.getSession.mockResolvedValueOnce({
      data: { session: { user: supabaseUser } },
      error: null,
    });

    const { unmount } = renderProvider();

    await waitFor(() => {
      expect(screen.getByTestId('initialized')).toHaveTextContent('true');
      expect(screen.getByTestId('user-name')).toHaveTextContent('Ada Reader');
    });
    expect(mocks.getSession).toHaveBeenCalledOnce();
    expect(mocks.onAuthStateChange).toHaveBeenCalledOnce();

    unmount();
    expect(mocks.unsubscribe).toHaveBeenCalledOnce();
  });

  it('uses password sign-in and lets the auth route guard redirect once', async () => {
    mocks.signInWithPassword.mockImplementationOnce(async () => {
      authStateChangeHandler?.('SIGNED_IN', { user: supabaseUser });
      return { data: { user: supabaseUser, session: {} }, error: null };
    });

    renderAuthRouteProvider();
    await screen.findByText('true');

    await userEvent.click(screen.getByRole('button', { name: 'Sign in test' }));

    await waitFor(() => {
      expect(mocks.signInWithPassword).toHaveBeenCalledWith({
        email: 'reader@example.com',
        password: 'secure-password',
      });
      expect(mocks.replace).toHaveBeenCalledTimes(1);
      expect(mocks.replace).toHaveBeenCalledWith('/entries');
    });
  });

  it('maps the signed-in user without owning navigation', async () => {
    renderProvider();
    await screen.findByText('true');

    await userEvent.click(screen.getByRole('button', { name: 'Sign in test' }));

    await waitFor(() => {
      expect(mocks.signInWithPassword).toHaveBeenCalledWith({
        email: 'reader@example.com',
        password: 'secure-password',
      });
      expect(screen.getByTestId('user-name')).toHaveTextContent('Ada Reader');
    });
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('sends signup metadata and returns a confirmation result', async () => {
    renderProvider();
    await screen.findByText('true');

    await userEvent.click(screen.getByRole('button', { name: 'Sign up test' }));

    await waitFor(() => {
      expect(mocks.signUp).toHaveBeenCalledWith({
        email: 'reader@example.com',
        password: 'secure-password',
        options: {
          data: { full_name: 'Ada Reader' },
          emailRedirectTo: `${window.location.origin}/signup`,
        },
      });
      expect(screen.getByTestId('signup-result')).toHaveTextContent(
        'reader@example.com',
      );
    });
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it('signs out, clears user-scoped query data, and lets the guard redirect once', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['entries'], { items: [] });
    mocks.getSession.mockResolvedValueOnce({
      data: { session: { user: supabaseUser } },
      error: null,
    });
    mocks.signOut.mockImplementationOnce(async () => {
      authStateChangeHandler?.('SIGNED_OUT', null);
      return { error: null };
    });

    renderProtectedProvider(queryClient);
    await screen.findByText('Ada Reader');

    await userEvent.click(
      screen.getByRole('button', { name: 'Sign out test' }),
    );

    await waitFor(() => {
      expect(mocks.signOut).toHaveBeenCalledOnce();
      expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
      expect(mocks.replace).toHaveBeenCalledTimes(1);
      expect(mocks.replace).toHaveBeenCalledWith('/login');
    });
  });

  it('preserves cache for same-user refresh and clears it on account change', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['entries', 'list'], { owner: 'user-1' });
    mocks.getSession.mockResolvedValueOnce({
      data: { session: { user: supabaseUser } },
      error: null,
    });
    renderProvider(queryClient);
    await screen.findByText('Ada Reader');

    act(() => {
      authStateChangeHandler?.('TOKEN_REFRESHED', { user: supabaseUser });
    });
    expect(queryClient.getQueryData(['entries', 'list'])).toEqual({
      owner: 'user-1',
    });

    act(() => {
      authStateChangeHandler?.('SIGNED_IN', {
        user: secondSupabaseUser,
      });
    });

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(screen.getByTestId('user-name')).toHaveTextContent('Second Reader');
  });

  it('handles session restoration rejection without leaking cached data', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['entries'], { owner: 'unknown' });
    mocks.getSession.mockRejectedValueOnce(new Error('storage unavailable'));

    renderProvider(queryClient);

    await waitFor(() => {
      expect(screen.getByTestId('initialized')).toHaveTextContent('true');
      expect(screen.getByTestId('user-name')).toHaveTextContent('none');
      expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    });
  });
});
