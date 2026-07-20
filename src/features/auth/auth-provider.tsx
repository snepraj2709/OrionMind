'use client';

import { useQueryClient } from '@tanstack/react-query';
import type { User } from '@supabase/supabase-js';
import {
  createContext,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { routes } from '@/config/routes';
import { safeAuthErrorMessage } from '@/services/auth/errors';
import type { SignInInput, SignUpInput } from '@/services/auth/schemas';
import type {
  AuthActionResult,
  AuthUser,
  SignUpActionResult,
} from '@/services/auth/types';
import { getSupabaseBrowserClient } from '@/services/supabase';

export interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isInitialized: boolean;
  isPending: boolean;
  signIn: (input: SignInInput) => Promise<AuthActionResult>;
  signUp: (input: SignUpInput) => Promise<SignUpActionResult>;
  signOut: () => Promise<void>;
  updateUser: (update: Pick<AuthUser, 'name'>) => void;
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

export interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const currentUserIdRef = useRef<string | null>(null);

  const applyAuthUser = useCallback(
    (nextSupabaseUser: User | null, forceClear = false) => {
      const nextUser = nextSupabaseUser
        ? mapSupabaseUser(nextSupabaseUser)
        : null;
      const previousUserId = currentUserIdRef.current;
      const nextUserId = nextUser?.id ?? null;
      const accountChanged = Boolean(
        previousUserId && nextUserId && previousUserId !== nextUserId,
      );
      const sessionEnded = Boolean(previousUserId && !nextUserId);

      if (forceClear || accountChanged || sessionEnded) {
        queryClient.clear();
      }

      currentUserIdRef.current = nextUserId;
      setUser(nextUser);
    },
    [queryClient],
  );

  useEffect(() => {
    let active = true;
    let receivedAuthEvent = false;

    try {
      const client = getSupabaseBrowserClient();
      const {
        data: { subscription },
      } = client.auth.onAuthStateChange((event, session) => {
        if (!active) return;
        receivedAuthEvent = true;
        applyAuthUser(session?.user ?? null, event === 'SIGNED_OUT');
        setIsInitialized(true);
      });

      void client.auth
        .getSession()
        .then(({ data, error }) => {
          if (!active || receivedAuthEvent) return;
          applyAuthUser(
            error ? null : (data.session?.user ?? null),
            Boolean(error),
          );
        })
        .catch(() => {
          if (!active || receivedAuthEvent) return;
          applyAuthUser(null, true);
        })
        .finally(() => {
          if (active) setIsInitialized(true);
        });

      return () => {
        active = false;
        subscription.unsubscribe();
      };
    } catch {
      queueMicrotask(() => {
        if (active) setIsInitialized(true);
      });
      return () => {
        active = false;
      };
    }
  }, [applyAuthUser]);

  const signIn = useCallback(
    async (input: SignInInput): Promise<AuthActionResult> => {
      setIsPending(true);
      try {
        const { data, error } =
          await getSupabaseBrowserClient().auth.signInWithPassword({
            email: input.email,
            password: input.password,
          });
        if (error) {
          return {
            ok: false,
            error: { message: safeAuthErrorMessage(error, 'sign-in') },
          };
        }
        if (!data.user) {
          return {
            ok: false,
            error: { message: 'Sign in is temporarily unavailable.' },
          };
        }

        const authenticatedUser = mapSupabaseUser(data.user);
        applyAuthUser(data.user);
        return { ok: true, user: authenticatedUser };
      } catch (error) {
        return {
          ok: false,
          error: { message: safeAuthErrorMessage(error, 'sign-in') },
        };
      } finally {
        setIsPending(false);
      }
    },
    [applyAuthUser],
  );

  const signUp = useCallback(
    async (input: SignUpInput): Promise<SignUpActionResult> => {
      setIsPending(true);
      try {
        const { error } = await getSupabaseBrowserClient().auth.signUp({
          email: input.email,
          password: input.password,
          options: {
            data: { full_name: input.name },
            emailRedirectTo: `${window.location.origin}${routes.signup.path}`,
          },
        });
        if (error) {
          return {
            ok: false,
            error: { message: safeAuthErrorMessage(error, 'sign-up') },
          };
        }

        return { ok: true, email: input.email };
      } catch (error) {
        return {
          ok: false,
          error: { message: safeAuthErrorMessage(error, 'sign-up') },
        };
      } finally {
        setIsPending(false);
      }
    },
    [],
  );

  const signOut = useCallback(async () => {
    setIsPending(true);
    try {
      const { error } = await getSupabaseBrowserClient().auth.signOut();
      if (error) throw new Error('Sign out failed.');

      applyAuthUser(null, true);
    } finally {
      setIsPending(false);
    }
  }, [applyAuthUser]);

  const updateUser = useCallback((update: Pick<AuthUser, 'name'>) => {
    setUser((current) => (current ? { ...current, ...update } : current));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isInitialized,
      isPending,
      signIn,
      signUp,
      signOut,
      updateUser,
    }),
    [isInitialized, isPending, signIn, signOut, signUp, updateUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
