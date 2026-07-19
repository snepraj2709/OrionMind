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
