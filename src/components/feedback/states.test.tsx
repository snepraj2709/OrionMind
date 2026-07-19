import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppButton } from '@/components/design-system';

import { AppErrorBoundary } from './app-error-boundary';
import { EmptyState } from './states';

function BrokenComponent(): never {
  throw new Error('Catalog render failed');
}

describe('feedback states', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('renders the standard empty-state content and action', () => {
    render(
      <EmptyState
        action={<AppButton>Write an entry</AppButton>}
        description="Begin with one honest sentence."
        title="Your journal is waiting"
      />,
    );

    expect(
      screen.getByRole('heading', { name: 'Your journal is waiting' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Begin with one honest sentence.')).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Write an entry' }),
    ).toBeEnabled();
  });

  it('catches rendering failures with an accessible recovery state', () => {
    render(
      <AppErrorBoundary>
        <BrokenComponent />
      </AppErrorBoundary>,
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(
      screen.getByText('This part of Orion could not be displayed.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
  });
});
