import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { AuthContextValue } from './auth-provider';
import { AuthRoutePrompt } from './auth-route-prompt';
import { SignInForm } from './sign-in-form';
import { SignUpForm } from './sign-up-form';

const authMocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
}));

vi.mock('./use-auth', () => ({
  useAuth: authMocks.useAuth,
}));

function renderWithAuth(children: ReactNode) {
  const value: AuthContextValue = {
    user: null,
    isAuthenticated: false,
    isPending: false,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn().mockResolvedValue(undefined),
    updateUser: vi.fn(),
  };

  authMocks.useAuth.mockReturnValue(value);

  return {
    ...render(children),
    value,
  };
}

describe('authentication forms', () => {
  it('uses the approved login copy and preserves the recovery destination', () => {
    renderWithAuth(
      <>
        <SignInForm redirectTo="/entries/new" />
        <AuthRoutePrompt
          actionLabel="Register"
          href="/signup"
          prompt="No account yet?"
        />
      </>,
    );

    expect(screen.getByLabelText('Email *')).toHaveAttribute(
      'placeholder',
      'you@example.com',
    );
    expect(screen.getByLabelText('Password *')).not.toHaveAttribute(
      'placeholder',
    );
    expect(
      screen.getByRole('link', { name: 'Forgot password?' }),
    ).toHaveAttribute('href', '/forgot-password?redirect=%2Fentries%2Fnew');

    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
    expect(screen.getByRole('link', { name: 'Register' })).toHaveAttribute(
      'href',
      '/signup',
    );
    expect(screen.getByText('No account yet?')).toBeVisible();
  });

  it('retains Full name and screenshot-aligned signup placeholders', () => {
    renderWithAuth(<SignUpForm />);

    expect(screen.getByLabelText('Full name *')).toHaveAttribute(
      'placeholder',
      'Your name',
    );
    expect(screen.getByLabelText('Email *')).toHaveAttribute(
      'placeholder',
      'you@example.com',
    );
    expect(screen.getByLabelText('Password *')).not.toHaveAttribute(
      'placeholder',
    );
    expect(screen.getByText('Use at least 8 characters.')).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Create account' }),
    ).toBeEnabled();
  });
});
