import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
    isInitialized: true,
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

  it('replaces signup with a check-your-email confirmation', async () => {
    const { value } = renderWithAuth(<SignUpForm />);
    vi.mocked(value.signUp).mockResolvedValue({
      ok: true,
      email: 'reader@example.com',
    });

    await userEvent.type(screen.getByLabelText('Full name *'), 'Ada Reader');
    await userEvent.type(
      screen.getByLabelText('Email *'),
      'reader@example.com',
    );
    await userEvent.type(
      screen.getByLabelText('Password *'),
      'secure-password',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Create account' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Check your email',
    );
    expect(screen.getByRole('status')).toHaveTextContent('reader@example.com');
    expect(value.signUp).toHaveBeenCalledWith({
      name: 'Ada Reader',
      email: 'reader@example.com',
      password: 'secure-password',
    });
    expect(screen.queryByLabelText('Password *')).not.toBeInTheDocument();
  });
});
