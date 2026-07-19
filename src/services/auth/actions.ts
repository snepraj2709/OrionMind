'use server';

import { createHash } from 'node:crypto';

import { clearMockSession, setMockSession } from './session';
import { signInSchema, signUpSchema } from './schemas';
import type { AuthActionResult, AuthUser } from './types';

function userId(email: string) {
  return createHash('sha256').update(email).digest('hex').slice(0, 16);
}

function displayName(email: string) {
  const name = email
    .split('@')[0]
    ?.replace(/[._-]+/g, ' ')
    .trim();
  return name || 'Orion user';
}

export async function signIn(input: unknown): Promise<AuthActionResult> {
  const parsed = signInSchema.safeParse(input);

  if (!parsed.success) {
    return { ok: false, error: { message: 'Check your email and password.' } };
  }

  const email = parsed.data.email.toLowerCase();
  const user: AuthUser = {
    id: userId(email),
    email,
    name: displayName(email),
  };

  await setMockSession(user);
  return { ok: true, user };
}

export async function signUp(input: unknown): Promise<AuthActionResult> {
  const parsed = signUpSchema.safeParse(input);

  if (!parsed.success) {
    return { ok: false, error: { message: 'Check the account details.' } };
  }

  const email = parsed.data.email.toLowerCase();
  const user: AuthUser = {
    id: userId(email),
    email,
    name: parsed.data.name,
  };

  await setMockSession(user);
  return { ok: true, user };
}

export async function signOut() {
  await clearMockSession();
}
