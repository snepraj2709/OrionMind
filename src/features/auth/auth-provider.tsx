'use client';

import { useRouter } from 'next/navigation';
import type { Route } from 'next';
import {
  createContext,
  type ReactNode,
  useCallback,
  useMemo,
  useState,
} from 'react';

import { routes, safeRedirectPath } from '@/config/routes';
import {
  signIn as performSignIn,
  signOut as performSignOut,
  signUp as performSignUp,
} from '@/services/auth/actions';
import type { SignInInput, SignUpInput } from '@/services/auth/schemas';
import type { AuthActionResult, AuthUser } from '@/services/auth/types';

export interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isPending: boolean;
  signIn: (
    input: SignInInput,
    redirectTo?: string,
  ) => Promise<AuthActionResult>;
  signUp: (
    input: SignUpInput,
    redirectTo?: string,
  ) => Promise<AuthActionResult>;
  signOut: () => Promise<void>;
  updateUser: (update: Pick<AuthUser, 'name'>) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

function unavailableResult(): AuthActionResult {
  return {
    ok: false,
    error: { message: 'Authentication is temporarily unavailable.' },
  };
}

export interface AuthProviderProps {
  children: ReactNode;
  initialUser: AuthUser | null;
}

export function AuthProvider({ children, initialUser }: AuthProviderProps) {
  const router = useRouter();
  const [user, setUser] = useState(initialUser);
  const [isPending, setIsPending] = useState(false);

  const completeAuthentication = useCallback(
    (result: AuthActionResult, redirectTo?: string) => {
      if (!result.ok) return;

      setUser(result.user);
      router.replace(safeRedirectPath(redirectTo) as Route);
      router.refresh();
    },
    [router],
  );

  const signIn = useCallback(
    async (input: SignInInput, redirectTo?: string) => {
      setIsPending(true);
      try {
        const result = await performSignIn(input);
        completeAuthentication(result, redirectTo);
        return result;
      } catch {
        return unavailableResult();
      } finally {
        setIsPending(false);
      }
    },
    [completeAuthentication],
  );

  const signUp = useCallback(
    async (input: SignUpInput, redirectTo?: string) => {
      setIsPending(true);
      try {
        const result = await performSignUp(input);
        completeAuthentication(result, redirectTo);
        return result;
      } catch {
        return unavailableResult();
      } finally {
        setIsPending(false);
      }
    },
    [completeAuthentication],
  );

  const signOut = useCallback(async () => {
    setIsPending(true);
    try {
      await performSignOut();
      setUser(null);
      router.replace(routes.login.path as Route);
      router.refresh();
    } finally {
      setIsPending(false);
    }
  }, [router]);

  const updateUser = useCallback((update: Pick<AuthUser, 'name'>) => {
    setUser((current) => (current ? { ...current, ...update } : current));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isPending,
      signIn,
      signUp,
      signOut,
      updateUser,
    }),
    [isPending, signIn, signOut, signUp, updateUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
