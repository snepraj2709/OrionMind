import type { Session } from '@supabase/supabase-js';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

export type AuthStatus =
  'resolving' | 'unconfigured' | 'anonymous' | 'authenticated';

export type AuthFlow =
  | 'default'
  | 'forgot_password'
  | 'recovery_email_sent'
  | 'recovery_token_validation'
  | 'set_new_password'
  | 'recovery_complete'
  | 'confirmation_email_sent'
  | 'confirmation_token_validation'
  | 'confirmation_success'
  | 'expired_or_invalid_link'
  | 'session_expired';

export type AuthActionErrorKind =
  'validation' | 'rate_limited' | 'offline' | 'provider_error';

export interface AuthActionError {
  kind: AuthActionErrorKind;
  message: string;
}

export type AuthActionResult =
  { ok: true; user: AuthUser } | { ok: false; error: AuthActionError };

export type SignUpActionResult =
  | { ok: true; email: string; session: Session | null }
  | { ok: false; error: AuthActionError };

export type AuthSimpleActionResult =
  { ok: true } | { ok: false; error: AuthActionError };
