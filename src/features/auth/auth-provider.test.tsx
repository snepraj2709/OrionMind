import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode, useState } from 'react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createFakeSupabase, makeSession } from '@/test/fake-supabase';

import { AuthProvider } from './auth-provider';
import { AuthRouteGuard } from './auth-route-guard';
import { useAuth } from './use-auth';

const navigationMocks = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: navigationMocks.replace }),
}));

function AuthHarness() {
  const auth = useAuth();
  const [result, setResult] = useState('');

  return (
    <>
      <output data-testid="status">{auth.status}</output>
      <output data-testid="flow">{auth.flow}</output>
      <output data-testid="user-name">{auth.user?.name ?? 'none'}</output>
      <output data-testid="result">{result}</output>
      <button
        onClick={() =>
          void auth
            .signIn({
              email: 'reader@example.com',
              password: 'secure-password',
            })
            .then((value) =>
              setResult(value.ok ? value.user.email : value.error.message),
            )
        }
        type="button"
      >
        Sign in test
      </button>
      <button
        onClick={() =>
          void auth
            .signUp({
              email: 'reader@example.com',
              password: 'secure-password',
            })
            .then((value) =>
              setResult(value.ok ? value.email : value.error.message),
            )
        }
        type="button"
      >
        Sign up test
      </button>
      <button onClick={() => void auth.signOut()} type="button">
        Sign out test
      </button>
      <button
        onClick={() =>
          void auth
            .apiFetch('/api/v1/profile')
            .catch((error: Error) => setResult(error.name))
        }
        type="button"
      >
        API test
      </button>
    </>
  );
}

function renderProvider(
  client: Parameters<typeof AuthProvider>[0]['client'],
  options: { queryClient?: QueryClient; strict?: boolean } = {},
) {
  const queryClient = options.queryClient ?? new QueryClient();
  const content = (
    <QueryClientProvider client={queryClient}>
      <AuthProvider client={client}>
        <AuthHarness />
      </AuthProvider>
    </QueryClientProvider>
  );
  return {
    queryClient,
    ...render(options.strict ? <StrictMode>{content}</StrictMode> : content),
  };
}

interface HydrationAuthRouteProps {
  client: NonNullable<Parameters<typeof AuthProvider>[0]['client']>;
  queryClient: QueryClient;
}

function HydrationAuthRoute({ client, queryClient }: HydrationAuthRouteProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider client={typeof window === 'undefined' ? null : client}>
        <AuthRouteGuard>
          <main>Login form</main>
        </AuthRouteGuard>
      </AuthProvider>
    </QueryClientProvider>
  );
}

afterEach(() => {
  window.history.replaceState({}, '', '/');
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('AuthProvider session ownership', () => {
  it('hydrates configured auth routes with the same initial session state', async () => {
    const fake = createFakeSupabase(null);
    const browserWindow = window;
    vi.stubGlobal('window', undefined);
    const serverMarkup = renderToString(
      <HydrationAuthRoute
        client={fake.client}
        queryClient={new QueryClient()}
      />,
    );
    vi.stubGlobal('window', browserWindow);

    const container = document.createElement('div');
    container.innerHTML = serverMarkup;
    document.body.append(container);
    const onRecoverableError = vi.fn();

    const root = hydrateRoot(
      container,
      <HydrationAuthRoute
        client={fake.client}
        queryClient={new QueryClient()}
      />,
      { onRecoverableError },
    );

    await act(async () => undefined);

    expect(onRecoverableError).not.toHaveBeenCalled();
    expect(fake.getSession).toHaveBeenCalledOnce();
    expect(container).toHaveTextContent('Login form');

    root.unmount();
    container.remove();
  });

  it('fails safely when public Supabase configuration is missing', async () => {
    renderProvider(null);
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unconfigured'),
    );
    expect(screen.getByTestId('user-name')).toHaveTextContent('none');
  });

  it('hydrates safely when public Supabase configuration is missing', async () => {
    const browserWindow = window;
    vi.stubGlobal('window', undefined);
    const serverMarkup = renderToString(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider client={null}>
          <AuthHarness />
        </AuthProvider>
      </QueryClientProvider>,
    );
    vi.stubGlobal('window', browserWindow);

    const container = document.createElement('div');
    container.innerHTML = serverMarkup;
    document.body.append(container);
    const consoleError = vi
      .spyOn(console, 'error')
      .mockImplementation(() => undefined);

    const root = hydrateRoot(
      container,
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider client={null}>
          <AuthHarness />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await act(async () => undefined);

    expect(consoleError).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="status"]')).toHaveTextContent(
      'unconfigured',
    );

    root.unmount();
    container.remove();
    consoleError.mockRestore();
  });

  it('ignores browser mock-user flags when Supabase has no session', async () => {
    window.localStorage.setItem('orion:user', 'mock-user');
    window.sessionStorage.setItem('authenticated', 'true');
    const fake = createFakeSupabase(null);

    renderProvider(fake.client);

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous'),
    );
    expect(screen.getByTestId('user-name')).toHaveTextContent('none');
  });

  it('restores the initial session exactly once under React StrictMode', async () => {
    const fake = createFakeSupabase(makeSession());
    renderProvider(fake.client, { strict: true });

    expect(await screen.findByTestId('status')).toHaveTextContent(
      'authenticated',
    );
    expect(fake.getSession).toHaveBeenCalledOnce();
    expect(screen.getByTestId('user-name')).toHaveTextContent('user a');
  });

  it('uses exact password login and signup redirect SDK calls', async () => {
    const fake = createFakeSupabase(makeSession());
    renderProvider(fake.client);
    await screen.findByText('authenticated');

    await userEvent.click(screen.getByRole('button', { name: 'Sign in test' }));
    expect(fake.signInWithPassword).toHaveBeenCalledWith({
      email: 'reader@example.com',
      password: 'secure-password',
    });

    await userEvent.click(screen.getByRole('button', { name: 'Sign up test' }));
    expect(fake.signUp).toHaveBeenCalledWith({
      email: 'reader@example.com',
      password: 'secure-password',
      options: { emailRedirectTo: `${window.location.origin}/signup` },
    });
  });

  it('supports confirmation-required signup without assuming a session', async () => {
    const fake = createFakeSupabase(null);
    renderProvider(fake.client);
    await screen.findByText('anonymous');

    await userEvent.click(screen.getByRole('button', { name: 'Sign up test' }));

    expect(await screen.findByTestId('flow')).toHaveTextContent(
      'confirmation_email_sent',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
  });

  it('clears query and user storage on logout and account switching', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['entries'], { owner: 'user-a' });
    window.localStorage.setItem('orion:user:entries', 'private');
    window.localStorage.setItem('unrelated', 'preserved');
    const fake = createFakeSupabase(makeSession());
    renderProvider(fake.client, { queryClient });
    await screen.findByText('authenticated');
    expect(fake.onAuthStateChange).toHaveBeenCalledOnce();

    act(() => fake.emit('SIGNED_IN', makeSession('user-b')));
    await waitFor(() =>
      expect(screen.getByTestId('user-name')).toHaveTextContent('user b'),
    );
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(window.localStorage.getItem('orion:user:entries')).toBeNull();
    expect(window.localStorage.getItem('unrelated')).toBe('preserved');

    queryClient.setQueryData(['entries'], { owner: 'user-b' });
    await userEvent.click(
      screen.getByRole('button', { name: 'Sign out test' }),
    );
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous'),
    );
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(fake.signOut).toHaveBeenCalledOnce();
  });

  it('preserves same-user query state during TOKEN_REFRESHED', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['entries'], { owner: 'user-a' });
    const fake = createFakeSupabase(makeSession());
    renderProvider(fake.client, { queryClient });
    await screen.findByText('authenticated');

    act(() => fake.emit('TOKEN_REFRESHED', makeSession()));

    expect(queryClient.getQueryData(['entries'])).toEqual({ owner: 'user-a' });
  });

  it('fails closed and clears cache when restoration rejects', async () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(['entries'], { owner: 'unknown' });
    const fake = createFakeSupabase(
      null,
      Promise.reject(new Error('private storage failure')),
    );
    renderProvider(fake.client, { queryClient });

    expect(await screen.findByTestId('status')).toHaveTextContent('anonymous');
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it('validates and scrubs token-hash confirmation once under StrictMode', async () => {
    window.history.replaceState(
      {},
      '',
      '/signup?token_hash=secret-hash&type=signup&error_description=private',
    );
    const fake = createFakeSupabase(makeSession());
    renderProvider(fake.client, { strict: true });

    expect(await screen.findByTestId('flow')).toHaveTextContent(
      'email_confirmed',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(fake.verifyOtp).toHaveBeenCalledOnce();
    expect(fake.verifyOtp).toHaveBeenCalledWith({
      token_hash: 'secret-hash',
      type: 'signup',
    });
    expect(fake.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      '/login?state=email_confirmed',
    );
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
  });

  it('keeps the signed-in session after a confirmation callback is finalized', async () => {
    window.history.replaceState(
      {},
      '',
      '/signup?token_hash=secret-hash&type=signup',
    );
    const fake = createFakeSupabase(makeSession());
    fake.signOut.mockImplementationOnce(async () => {
      fake.emit('SIGNED_OUT', null);
      return { error: null };
    });

    renderProvider(fake.client);

    expect(await screen.findByTestId('flow')).toHaveTextContent(
      'email_confirmed',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');

    await userEvent.click(screen.getByRole('button', { name: 'Sign in test' }));

    expect(await screen.findByTestId('result')).toHaveTextContent(
      'user-a@example.test',
    );
    expect(screen.getByTestId('flow')).toHaveTextContent('default');
    expect(screen.getByTestId('status')).toHaveTextContent('authenticated');

    act(() => fake.emit('TOKEN_REFRESHED', makeSession()));

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated'),
    );
  });

  it('initializes and scrubs an automatic PKCE confirmation once', async () => {
    window.history.replaceState({}, '', '/signup?code=one-time-code');
    const fake = createFakeSupabase(makeSession());

    renderProvider(fake.client, { strict: true });

    expect(await screen.findByTestId('flow')).toHaveTextContent(
      'email_confirmed',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(fake.initialize).toHaveBeenCalledOnce();
    expect(fake.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      '/login?state=email_confirmed',
    );
    expect(window.location.search).toBe('');
  });

  it('validates token-hash recovery and opens the password update flow', async () => {
    window.history.replaceState(
      {},
      '',
      '/login?token_hash=recovery-hash&type=recovery',
    );
    const fake = createFakeSupabase(makeSession());

    renderProvider(fake.client, { strict: true });

    expect(await screen.findByTestId('flow')).toHaveTextContent(
      'set_new_password',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('authenticated');
    expect(fake.verifyOtp).toHaveBeenCalledOnce();
    expect(fake.verifyOtp).toHaveBeenCalledWith({
      token_hash: 'recovery-hash',
      type: 'recovery',
    });
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
  });

  it('fails closed when callback credentials arrive on the wrong auth route', async () => {
    window.history.replaceState(
      {},
      '',
      '/login?token_hash=secret-hash&type=signup&error_description=private',
    );
    const fake = createFakeSupabase(makeSession());

    renderProvider(fake.client);

    expect(await screen.findByTestId('flow')).toHaveTextContent(
      'expired_or_invalid_link',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(fake.verifyOtp).not.toHaveBeenCalled();
    expect(fake.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(window.location.search).toBe('');

    act(() => fake.emit('SIGNED_IN', makeSession()));
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('anonymous'),
    );
  });

  it('maps provider failures without rendering or logging raw details', async () => {
    const fake = createFakeSupabase(makeSession());
    fake.signInWithPassword.mockResolvedValueOnce({
      data: { session: null, user: null },
      error: Object.assign(new Error('access-token raw provider detail'), {
        status: 500,
      }),
    });
    const log = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    renderProvider(fake.client);
    await screen.findByText('authenticated');

    await userEvent.click(screen.getByRole('button', { name: 'Sign in test' }));

    expect(await screen.findByTestId('result')).toHaveTextContent(
      'Sign in is temporarily unavailable.',
    );
    expect(document.body).not.toHaveTextContent('access-token');
    expect(log).not.toHaveBeenCalled();
  });

  it('clears local state and redirects safely after a terminal API 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response(null, { status: 401 })),
    );
    const queryClient = new QueryClient();
    queryClient.setQueryData(['profile'], { owner: 'user-a' });
    window.localStorage.setItem('orion:user:profile', 'private');
    window.history.replaceState({}, '', '/profile');
    const fake = createFakeSupabase(makeSession());
    renderProvider(fake.client, { queryClient });
    await screen.findByText('authenticated');

    await userEvent.click(screen.getByRole('button', { name: 'API test' }));

    expect(await screen.findByTestId('result')).toHaveTextContent(
      'SessionExpiredError',
    );
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous');
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(window.localStorage.getItem('orion:user:profile')).toBeNull();
    expect(fake.refreshSession).toHaveBeenCalledOnce();
    expect(fake.signOut).toHaveBeenCalledWith({ scope: 'local' });
    expect(navigationMocks.replace).toHaveBeenCalledWith(
      '/login?returnTo=%2Fprofile&state=session_expired',
    );
  });
});
