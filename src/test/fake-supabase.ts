import type {
  AuthChangeEvent,
  Session,
  SupabaseClient,
} from '@supabase/supabase-js';
import { vi, type Mock } from 'vitest';

export function makeSession(
  userId = 'user-a',
  email = `${userId}@example.test`,
): Session {
  return {
    access_token: `access-${userId}`,
    refresh_token: `refresh-${userId}`,
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    token_type: 'bearer',
    user: {
      id: userId,
      app_metadata: {},
      user_metadata: {},
      aud: 'authenticated',
      created_at: '2026-07-13T00:00:00.000Z',
      email,
    },
  };
}

type SessionCallback = (
  event: AuthChangeEvent,
  session: Session | null,
) => void;

interface FakeOptions {
  initializeError?: unknown;
  sessionError?: unknown;
  verifyOtpError?: unknown;
  signupSession?: Session | null;
}

export interface FakeSupabase {
  client: SupabaseClient;
  emit: (event: AuthChangeEvent, session: Session | null) => void;
  getSession: Mock;
  initialize: Mock;
  onAuthStateChange: Mock;
  refreshSession: Mock;
  resetPasswordForEmail: Mock;
  signInWithPassword: Mock;
  signOut: Mock;
  signUp: Mock;
  updateUser: Mock;
  verifyOtp: Mock;
}

export function createFakeSupabase(
  initialSession: Session | null,
  sessionRequest?: Promise<unknown>,
  options: FakeOptions = {},
): FakeSupabase {
  let callback: SessionCallback | null = null;
  const initialize = vi.fn(() =>
    Promise.resolve({ error: options.initializeError ?? null }),
  );
  const getSession = vi.fn(
    () =>
      sessionRequest ??
      Promise.resolve({
        data: { session: initialSession },
        error: options.sessionError ?? null,
      }),
  );
  const refreshSession = vi.fn(() =>
    Promise.resolve({
      data: {
        session: initialSession,
        user: initialSession?.user ?? null,
      },
      error: null,
    }),
  );
  const signInWithPassword = vi.fn(() =>
    Promise.resolve({
      data: {
        session: initialSession,
        user: initialSession?.user ?? null,
      },
      error: null,
    }),
  );
  const signUp = vi.fn(() =>
    Promise.resolve({
      data: {
        session: options.signupSession ?? null,
        user: options.signupSession?.user ?? null,
      },
      error: null,
    }),
  );
  const resetPasswordForEmail = vi.fn(() =>
    Promise.resolve({ data: {}, error: null }),
  );
  const updateUser = vi.fn(() =>
    Promise.resolve({
      data: { user: initialSession?.user ?? null },
      error: null,
    }),
  );
  const signOut = vi.fn(() => Promise.resolve({ error: null }));
  const verifyOtp = vi.fn(() =>
    Promise.resolve({
      data: {
        session: initialSession,
        user: initialSession?.user ?? null,
      },
      error: options.verifyOtpError ?? null,
    }),
  );

  const onAuthStateChange = vi.fn((nextCallback: SessionCallback) => {
    callback = nextCallback;
    return {
      data: {
        subscription: {
          id: 'fake-subscription',
          callback: nextCallback,
          unsubscribe: vi.fn(),
        },
      },
    };
  });
  const client = {
    auth: {
      getSession,
      initialize,
      onAuthStateChange,
      refreshSession,
      resetPasswordForEmail,
      signInWithPassword,
      signOut,
      signUp,
      updateUser,
      verifyOtp,
    },
  } as unknown as SupabaseClient;

  return {
    client,
    emit(event, session) {
      callback?.(event, session);
    },
    getSession,
    initialize,
    onAuthStateChange,
    refreshSession,
    resetPasswordForEmail,
    signInWithPassword,
    signOut,
    signUp,
    updateUser,
    verifyOtp,
  };
}
