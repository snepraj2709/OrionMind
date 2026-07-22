'use client';

import { useQueryClient } from '@tanstack/react-query';
import type { Session, SupabaseClient, User } from '@supabase/supabase-js';
import type { Route } from 'next';
import { useRouter } from 'next/navigation';
import {
  createContext,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createLoginRedirect, routes } from '@/config/routes';
import {
  createAuthRedirectUrl,
  hasSensitiveAuthMaterial,
  readInitialAuthFlow,
  readSupabaseAuthCallback,
  scrubSensitiveAuthMaterial,
} from '@/services/auth/auth-url';
import { safeAuthActionError } from '@/services/auth/errors';
import type {
  PasswordRecoveryInput,
  PasswordUpdateInput,
  SignInInput,
  SignUpInput,
} from '@/services/auth/schemas';
import {
  initializeAuthCallbackOnce,
  getInitialSessionOnce,
  verifyAuthOtpOnce,
} from '@/services/auth/session-bootstrap';
import { clearUserScopedState } from '@/services/auth/session-scope';
import type {
  AuthActionResult,
  AuthFlow,
  AuthSimpleActionResult,
  AuthStatus,
  AuthUser,
  SignUpActionResult,
} from '@/services/auth/types';
import {
  createAuthorizedApiRequest,
  type ApiRequest,
  setApiSessionExpiredHandler,
} from '@/services/api-client';
import { resolveSupabaseBrowserClient } from '@/services/supabase';

export interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  user: AuthUser | null;
  flow: AuthFlow;
  isAuthenticated: boolean;
  isInitialized: boolean;
  isPending: boolean;
  isRequiredRecoveryActive: boolean;
  setFlow: (flow: AuthFlow) => void;
  signIn: (input: SignInInput) => Promise<AuthActionResult>;
  signUp: (input: SignUpInput) => Promise<SignUpActionResult>;
  requestPasswordReset: (
    input: PasswordRecoveryInput,
  ) => Promise<AuthSimpleActionResult>;
  updatePassword: (
    input: PasswordUpdateInput,
  ) => Promise<AuthSimpleActionResult>;
  signOut: () => Promise<void>;
  updateUser: (update: Pick<AuthUser, 'name'>) => void;
  apiFetch: ApiRequest;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

function displayName(user: User) {
  const metadataName = user.user_metadata.full_name;
  if (typeof metadataName === 'string' && metadataName.trim()) {
    return metadataName.trim();
  }

  const emailName = user.email
    ?.split('@')[0]
    ?.replace(/[._-]+/g, ' ')
    .trim();
  return emailName || 'Orion user';
}

export function mapSupabaseUser(user: User): AuthUser {
  return {
    id: user.id,
    email: user.email ?? '',
    name: displayName(user),
  };
}

function configurationError() {
  return {
    ok: false as const,
    error: {
      kind: 'provider_error' as const,
      message: 'Add the public Supabase URL and publishable key, then reload.',
    },
  };
}

export interface AuthProviderProps {
  children: ReactNode;
  client?: SupabaseClient | null;
}

export function AuthProvider({
  children,
  client: suppliedClient,
}: AuthProviderProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const client = useMemo(
    () => resolveSupabaseBrowserClient(suppliedClient),
    [suppliedClient],
  );
  const [status, setStatus] = useState<AuthStatus>(() =>
    client ? 'resolving' : 'unconfigured',
  );
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [flow, setFlow] = useState<AuthFlow>(() =>
    typeof window === 'undefined'
      ? 'default'
      : readInitialAuthFlow(window.location),
  );
  const [isPending, setIsPending] = useState(false);
  const initialFlow = useRef(flow);
  const initialCallback = useRef(
    typeof window === 'undefined'
      ? null
      : readSupabaseAuthCallback(window.location),
  );
  const currentUserIdRef = useRef<string | null>(null);
  const providerApiFetchRef = useRef<ApiRequest>(async () => {
    throw new Error('Supabase public configuration is missing.');
  });

  const clearPrivateState = useCallback(async () => {
    void queryClient.cancelQueries().catch(() => undefined);
    queryClient.clear();
    await clearUserScopedState();
  }, [queryClient]);

  const applyResolvedSession = useCallback(
    async (
      nextSession: Session | null,
      options: {
        forceClear?: boolean;
        isCurrent?: () => boolean;
      } = {},
    ) => {
      const previousUserId = currentUserIdRef.current;
      const nextUserId = nextSession?.user.id ?? null;
      const accountChanged = Boolean(
        previousUserId && nextUserId && previousUserId !== nextUserId,
      );
      const sessionEnded = Boolean(previousUserId && !nextUserId);

      const cleanup =
        options.forceClear || accountChanged || sessionEnded
          ? clearPrivateState()
          : null;
      if (options.isCurrent && !options.isCurrent()) {
        await cleanup;
        return;
      }

      currentUserIdRef.current = nextUserId;
      setSession(nextSession);
      setUser(nextSession ? mapSupabaseUser(nextSession.user) : null);
      setStatus(nextSession ? 'authenticated' : 'anonymous');
      await cleanup;
    },
    [clearPrivateState],
  );

  useEffect(() => {
    if (!client) return;

    let active = true;
    let authEventVersion = 0;
    let eventSession: Session | null | undefined;
    const shouldScrub = hasSensitiveAuthMaterial(window.location);
    const callbackRejected =
      shouldScrub &&
      initialFlow.current === 'expired_or_invalid_link' &&
      !initialCallback.current;
    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((event, nextSession) => {
      if (!active) return;
      authEventVersion += 1;
      const eventVersion = authEventVersion;
      if (callbackRejected) {
        eventSession = null;
        void applyResolvedSession(null, {
          forceClear: true,
          isCurrent: () => active && eventVersion === authEventVersion,
        });
        return;
      }
      if (event === 'PASSWORD_RECOVERY') setFlow('set_new_password');
      eventSession = nextSession;

      const previousUserId = currentUserIdRef.current;
      const nextUserId = nextSession?.user.id ?? null;
      if (previousUserId && previousUserId !== nextUserId) {
        setSession(null);
        setUser(null);
        setStatus('resolving');
      }
      void applyResolvedSession(nextSession, {
        isCurrent: () => active && eventVersion === authEventVersion,
      });
    });

    const bootstrapVersion = authEventVersion;
    void (async () => {
      let callbackSession: Session | null = null;
      let callbackError: unknown = null;

      if (callbackRejected) {
        await client.auth.signOut({ scope: 'local' });
      } else if (initialCallback.current?.method === 'automatic') {
        const result = await initializeAuthCallbackOnce(client);
        callbackError = result.error;
      } else if (initialCallback.current?.method === 'verify_otp') {
        const { tokenHash, type } = initialCallback.current;
        const result = await verifyAuthOtpOnce(client, tokenHash, type);
        callbackSession = result.data.session;
        callbackError = result.error;
      }

      const { data, error } = await getInitialSessionOnce(client);
      return {
        callbackError,
        callbackRejected,
        callbackSession,
        data,
        error,
      };
    })()
      .then(
        async ({
          callbackError,
          callbackRejected,
          callbackSession,
          data,
          error,
        }) => {
          if (!active) return;
          const resolvedSession = callbackRejected
            ? null
            : eventSession === undefined
              ? (callbackSession ?? data.session)
              : eventSession;
          if (authEventVersion === bootstrapVersion) {
            await applyResolvedSession(
              (error && !callbackSession) || callbackRejected
                ? null
                : resolvedSession,
              {
                forceClear: Boolean(
                  (error && !callbackSession) || callbackRejected,
                ),
                isCurrent: () =>
                  active && authEventVersion === bootstrapVersion,
              },
            );
          }

          const callbackValidated =
            !callbackError && !error && Boolean(resolvedSession);
          if (initialFlow.current === 'recovery_token_validation') {
            setFlow(
              callbackValidated
                ? 'set_new_password'
                : 'expired_or_invalid_link',
            );
          } else if (initialFlow.current === 'confirmation_token_validation') {
            setFlow(
              callbackValidated
                ? 'confirmation_success'
                : 'expired_or_invalid_link',
            );
          }
        },
      )
      .catch(() => {
        if (!active) return;
        if (authEventVersion === bootstrapVersion) {
          void applyResolvedSession(null, {
            forceClear: true,
            isCurrent: () => active && authEventVersion === bootstrapVersion,
          });
        }
        if (
          initialFlow.current === 'recovery_token_validation' ||
          initialFlow.current === 'confirmation_token_validation'
        ) {
          setFlow('expired_or_invalid_link');
        }
      })
      .finally(() => {
        if (active && shouldScrub) {
          scrubSensitiveAuthMaterial(window.location, window.history);
        }
      });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [applyResolvedSession, client]);

  const signIn = useCallback(
    async (input: SignInInput): Promise<AuthActionResult> => {
      if (!client) return configurationError();
      if (isPending) {
        return {
          ok: false,
          error: { kind: 'validation', message: 'Sign in is already running.' },
        };
      }

      setIsPending(true);
      try {
        const { data, error } = await client.auth.signInWithPassword({
          email: input.email,
          password: input.password,
        });
        if (error)
          return { ok: false, error: safeAuthActionError(error, 'sign-in') };
        if (!data.user || !data.session) {
          return {
            ok: false,
            error: {
              kind: 'provider_error',
              message: 'Sign in is temporarily unavailable.',
            },
          };
        }

        await applyResolvedSession(data.session);
        setFlow('default');
        return { ok: true, user: mapSupabaseUser(data.user) };
      } catch (error) {
        return { ok: false, error: safeAuthActionError(error, 'sign-in') };
      } finally {
        setIsPending(false);
      }
    },
    [applyResolvedSession, client, isPending],
  );

  const signUp = useCallback(
    async (input: SignUpInput): Promise<SignUpActionResult> => {
      if (!client) return configurationError();
      if (isPending) {
        return {
          ok: false,
          error: {
            kind: 'validation',
            message: 'Account creation is already running.',
          },
        };
      }

      setIsPending(true);
      try {
        const { data, error } = await client.auth.signUp({
          email: input.email,
          password: input.password,
          options: {
            emailRedirectTo: createAuthRedirectUrl(routes.signup.path),
          },
        });
        if (error)
          return { ok: false, error: safeAuthActionError(error, 'sign-up') };
        if (data.session) await applyResolvedSession(data.session);
        if (!data.session) setFlow('confirmation_email_sent');
        return { ok: true, email: input.email, session: data.session };
      } catch (error) {
        return { ok: false, error: safeAuthActionError(error, 'sign-up') };
      } finally {
        setIsPending(false);
      }
    },
    [applyResolvedSession, client, isPending],
  );

  const requestPasswordReset = useCallback(
    async (input: PasswordRecoveryInput): Promise<AuthSimpleActionResult> => {
      if (!client) return configurationError();
      setIsPending(true);
      try {
        const { error } = await client.auth.resetPasswordForEmail(input.email, {
          redirectTo: createAuthRedirectUrl(routes.login.path),
        });
        if (error) {
          return { ok: false, error: safeAuthActionError(error, 'recovery') };
        }
        setFlow('recovery_email_sent');
        return { ok: true };
      } catch (error) {
        return { ok: false, error: safeAuthActionError(error, 'recovery') };
      } finally {
        setIsPending(false);
      }
    },
    [client],
  );

  const updatePassword = useCallback(
    async (input: PasswordUpdateInput): Promise<AuthSimpleActionResult> => {
      if (!client) return configurationError();
      setIsPending(true);
      try {
        const { error } = await client.auth.updateUser({
          password: input.password,
        });
        if (error) {
          return {
            ok: false,
            error: safeAuthActionError(error, 'password-update'),
          };
        }
        setFlow('recovery_complete');
        return { ok: true };
      } catch (error) {
        return {
          ok: false,
          error: safeAuthActionError(error, 'password-update'),
        };
      } finally {
        setIsPending(false);
      }
    },
    [client],
  );

  const terminateLocalSession = useCallback(async () => {
    currentUserIdRef.current = null;
    await clearPrivateState();
    setSession(null);
    setUser(null);
    setStatus('anonymous');
  }, [clearPrivateState]);

  const signOut = useCallback(async () => {
    if (isPending) return;
    setIsPending(true);
    try {
      await terminateLocalSession();
      setFlow('default');
      if (client) await client.auth.signOut();
    } finally {
      setIsPending(false);
    }
  }, [client, isPending, terminateLocalSession]);

  const expireSession = useCallback(async () => {
    const pathname =
      typeof window === 'undefined'
        ? routes.entries.path
        : window.location.pathname;
    const search = typeof window === 'undefined' ? '' : window.location.search;
    await terminateLocalSession();
    setFlow('session_expired');
    if (client) {
      try {
        await client.auth.signOut({ scope: 'local' });
      } catch {
        // Local state is already terminated; continue to the safe login route.
      }
    }
    const redirect = new URL(
      createLoginRedirect(pathname, search),
      'https://orion.local',
    );
    redirect.searchParams.set('state', 'session_expired');
    router.replace(`${redirect.pathname}${redirect.search}` as Route);
  }, [client, router, terminateLocalSession]);

  useEffect(() => setApiSessionExpiredHandler(expireSession), [expireSession]);

  useEffect(() => {
    providerApiFetchRef.current = client
      ? createAuthorizedApiRequest({
          client,
          onSessionExpired: expireSession,
        })
      : async () => {
          throw new Error('Supabase public configuration is missing.');
        };
  }, [client, expireSession]);

  const providerApiFetch = useCallback<ApiRequest>(
    (path, init) => providerApiFetchRef.current(path, init),
    [],
  );

  const updateUser = useCallback((update: Pick<AuthUser, 'name'>) => {
    setUser((current) => (current ? { ...current, ...update } : current));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      user,
      flow,
      isAuthenticated: status === 'authenticated',
      isInitialized: status !== 'resolving',
      isPending,
      isRequiredRecoveryActive:
        flow === 'recovery_token_validation' || flow === 'set_new_password',
      setFlow,
      signIn,
      signUp,
      requestPasswordReset,
      updatePassword,
      signOut,
      updateUser,
      apiFetch: providerApiFetch,
    }),
    [
      flow,
      isPending,
      providerApiFetch,
      requestPasswordReset,
      session,
      signIn,
      signOut,
      signUp,
      status,
      updatePassword,
      updateUser,
      user,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
