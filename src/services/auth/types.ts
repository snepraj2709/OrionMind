export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

export interface AuthActionError {
  message: string;
}

export type AuthActionResult =
  { ok: true; user: AuthUser } | { ok: false; error: AuthActionError };

export type SignUpActionResult =
  { ok: true; email: string } | { ok: false; error: AuthActionError };
