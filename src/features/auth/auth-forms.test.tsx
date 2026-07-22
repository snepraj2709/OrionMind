import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { AuthContextValue } from './auth-provider';
import { LoginScreen } from './login-screen';
import { SignInForm } from './sign-in-form';
import { SignUpForm } from './sign-up-form';
import { SignupScreen } from './signup-screen';

const mocks = vi.hoisted(() => ({ replace: vi.fn(), useAuth: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock('./use-auth', () => ({ useAuth: mocks.useAuth }));

function authValue(
  overrides: Partial<AuthContextValue> = {},
): AuthContextValue {
  return {
    status: 'anonymous',
    session: null,
    user: null,
    flow: 'default',
    isAuthenticated: false,
    isInitialized: true,
    isPending: false,
    isRequiredRecoveryActive: false,
    setFlow: vi.fn(),
    signIn: vi.fn(),
    signUp: vi.fn(),
    requestPasswordReset: vi.fn(),
    updatePassword: vi.fn(),
    signOut: vi.fn(),
    updateUser: vi.fn(),
    apiFetch: vi.fn(),
    ...overrides,
  };
}

function renderWithAuth(children: ReactNode, overrides = {}) {
  const value = authValue(overrides);
  mocks.useAuth.mockReturnValue(value);
  return { ...render(children), value };
}

describe('authentication forms', () => {
  it('submits accessible email/password login through Supabase ownership', async () => {
    const signIn = vi.fn().mockResolvedValue({
      ok: true,
      user: { id: 'user-1', email: 'reader@example.com', name: 'Reader' },
    });
    renderWithAuth(<SignInForm onForgotPassword={vi.fn()} />, { signIn });

    const email = screen.getByLabelText('Email *');
    const password = screen.getByLabelText('Password *');
    expect(email).toHaveAttribute('type', 'email');
    expect(email).toHaveAttribute('autocomplete', 'email');
    expect(email).toBeRequired();
    expect(password).toHaveAttribute('type', 'password');
    expect(password).toHaveAttribute('autocomplete', 'current-password');
    expect(password).toBeRequired();

    await userEvent.type(email, 'reader@example.com');
    await userEvent.type(password, 'secure-password');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(signIn).toHaveBeenCalledWith({
      email: 'reader@example.com',
      password: 'secure-password',
    });
  });

  it('disables login submission while pending', () => {
    renderWithAuth(<SignInForm />, { isPending: true });
    expect(screen.getByRole('button', { name: 'Signing in' })).toBeDisabled();
  });

  it('opens forgot-password as a login state', async () => {
    const setFlow = vi.fn();
    renderWithAuth(<LoginScreen />, { setFlow });
    await userEvent.click(
      screen.getByRole('link', { name: 'Forgot password?' }),
    );
    expect(setFlow).toHaveBeenCalledWith('forgot_password');
  });

  it('submits signup with only email and a valid new password', async () => {
    const signUp = vi.fn().mockResolvedValue({
      ok: true,
      email: 'reader@example.com',
      session: null,
    });
    renderWithAuth(<SignUpForm />, { signUp });

    expect(screen.queryByLabelText(/Full name/)).not.toBeInTheDocument();
    const email = screen.getByLabelText('Email *');
    const password = screen.getByLabelText('Password *');
    expect(email).toHaveAttribute('type', 'email');
    expect(password).toHaveAttribute('autocomplete', 'new-password');
    expect(password).toHaveAttribute('type', 'password');

    await userEvent.type(email, 'reader@example.com');
    await userEvent.type(password, 'secure-password');
    await userEvent.click(
      screen.getByRole('button', { name: 'Create account' }),
    );
    expect(signUp).toHaveBeenCalledWith({
      email: 'reader@example.com',
      password: 'secure-password',
    });
  });

  it('rejects signup passwords shorter than eight characters', async () => {
    const signUp = vi.fn();
    renderWithAuth(<SignUpForm />, { signUp });
    await userEvent.type(
      screen.getByLabelText('Email *'),
      'reader@example.com',
    );
    await userEvent.type(screen.getByLabelText('Password *'), 'short');
    await userEvent.click(
      screen.getByRole('button', { name: 'Create account' }),
    );

    expect(
      await screen.findByText('Password must contain at least 8 characters.'),
    ).toBeVisible();
    expect(signUp).not.toHaveBeenCalled();
  });

  it('shows the generic confirmation-email state without revealing registration status', () => {
    renderWithAuth(<SignupScreen />, { flow: 'confirmation_email_sent' });
    expect(
      screen.getByRole('heading', { name: 'Confirm your email' }),
    ).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Open the newest confirmation link',
    );
    expect(screen.getByRole('status')).not.toHaveTextContent('@');
  });

  it('shows confirmation success on the login form', () => {
    renderWithAuth(<LoginScreen />, { flow: 'email_confirmed' });
    expect(screen.getByRole('status')).toHaveTextContent(
      'Your email is confirmed. Sign in to continue.',
    );
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeVisible();
  });

  it('requests recovery on login and updates matching new passwords', async () => {
    const requestPasswordReset = vi.fn().mockResolvedValue({ ok: true });
    const first = renderWithAuth(<LoginScreen />, {
      flow: 'forgot_password',
      requestPasswordReset,
    });
    await userEvent.type(
      screen.getByLabelText('Email *'),
      'reader@example.com',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Send recovery email' }),
    );
    expect(requestPasswordReset).toHaveBeenCalledWith({
      email: 'reader@example.com',
    });
    first.unmount();

    const updatePassword = vi.fn().mockResolvedValue({ ok: true });
    renderWithAuth(<LoginScreen />, {
      flow: 'set_new_password',
      status: 'authenticated',
      isAuthenticated: true,
      isRequiredRecoveryActive: true,
      updatePassword,
    });
    await userEvent.type(
      screen.getByLabelText('New password *'),
      'new-password',
    );
    await userEvent.type(
      screen.getByLabelText('Confirm new password *'),
      'new-password',
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'Update password' }),
    );
    expect(updatePassword).toHaveBeenCalledWith({
      password: 'new-password',
      confirmation: 'new-password',
    });
  });
});
