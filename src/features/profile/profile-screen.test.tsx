import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { PropsWithChildren } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { MockProfileRepository } from './mock-repository';
import { ProfileScreen } from './profile-screen';
import type { ProfileRepository } from './repository';

vi.mock('@/features/auth', () => ({
  SignOutButton: () => <button type="button">Log out</button>,
  useAuth: () => ({
    updateUser: vi.fn(),
    user: { id: 'user-1', email: 'maya@example.com', name: 'Maya Chen' },
  }),
}));

function renderScreen(repository: ProfileRepository) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  }
  return render(<ProfileScreen repository={repository} />, {
    wrapper: Wrapper,
  });
}

describe('ProfileScreen', () => {
  it('loads profile fields and exposes logout', async () => {
    renderScreen(new MockProfileRepository(undefined, 0));
    expect(await screen.findByLabelText('Display name *')).toHaveValue(
      'Maya Chen',
    );
    expect(screen.getByLabelText('Email')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument();
  });

  it('validates and saves dirty profile changes', async () => {
    const user = userEvent.setup();
    const repository = new MockProfileRepository(undefined, 0);
    const updateProfile = vi.spyOn(repository, 'updateProfile');
    renderScreen(repository);
    const input = await screen.findByLabelText('Display name *');
    await user.clear(input);
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Enter at least two characters.',
    );
    await user.type(input, 'Maya Rivera');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() =>
      expect(updateProfile).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'maya@example.com' }),
        expect.objectContaining({ displayName: 'Maya Rivera' }),
      ),
    );
    expect(
      await screen.findByText('All changes are saved.'),
    ).toBeInTheDocument();
  });

  it('shows a load error and retries', async () => {
    const getProfile = vi.fn().mockRejectedValue(new Error('nope'));
    renderScreen({ getProfile, updateProfile: vi.fn() });
    expect(
      await screen.findByRole('heading', {
        name: 'Profile settings are unavailable',
      }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(getProfile).toHaveBeenCalledTimes(2));
  });
});
