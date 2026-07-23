import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DataViewStatus } from './data-view-status';

const errorCopy = {
  description: 'The page could not be loaded.',
  title: 'Page unavailable',
};

function renderStatus(
  status:
    'loading' | 'initial-error' | 'refresh-error' | 'refreshing' | 'ready',
) {
  const onRetry = vi.fn();
  const view = render(
    <DataViewStatus
      initialError={errorCopy}
      onRetry={onRetry}
      refreshError="The page could not be refreshed."
      status={status}
    />,
  );

  return { onRetry, ...view };
}

describe('DataViewStatus', () => {
  it('renders initial loading in a centered, page-wide card', () => {
    renderStatus('loading');

    const heading = screen.getByRole('heading', { name: 'Loading' });
    expect(heading.closest('[role="status"]')).toHaveClass(
      'text-measure',
      'mx-auto',
      'items-center',
      'text-center',
    );
    expect(heading.closest('[data-slot="card"]')).toHaveClass(
      'radius-card',
      'border-border',
      'bg-card',
    );
    expect(screen.getByText('Orion is loading this page.')).toBeVisible();
    expect(document.querySelectorAll('.animate-spin')).toHaveLength(1);
  });

  it('renders background refresh in the same card with common copy', () => {
    renderStatus('refreshing');

    const heading = screen.getByRole('heading', { name: 'Refreshing' });
    expect(heading.closest('[data-slot="card"]')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Orion is checking for updates. Your current view will stay in place.',
      ),
    ).toBeVisible();
    expect(document.querySelectorAll('.animate-spin')).toHaveLength(1);
  });

  it.each([
    ['initial-error', 'Page unavailable', 'The page could not be loaded.'],
    ['refresh-error', 'Refresh failed', 'The page could not be refreshed.'],
  ] as const)(
    'renders %s in the centered error card and retries',
    (status, title, description) => {
      const { onRetry } = renderStatus(status);

      const heading = screen.getByRole('heading', { name: title });
      expect(heading.closest('[role="alert"]')).toHaveClass(
        'text-measure',
        'mx-auto',
        'items-center',
        'text-center',
      );
      expect(heading.closest('[data-slot="card"]')).toBeInTheDocument();
      expect(screen.getByText(description)).toBeVisible();

      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
      expect(onRetry).toHaveBeenCalledOnce();
    },
  );

  it('renders nothing when the data view is ready', () => {
    const { container } = renderStatus('ready');

    expect(container).toBeEmptyDOMElement();
  });
});
