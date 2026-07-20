import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  MockSavedItemsRepository,
  type SavedItemRecord,
  type SavedItemsRepository,
  type SavedItemsResult,
} from '@/services/saved-items';

import { SavedItemsScreen } from './saved-items-screen';

const item: SavedItemRecord = {
  id: 'idea-1',
  content: 'I want to protect slow mornings.',
  entryDate: '2025-07-10',
  entryId: 'entry-1',
  kind: 'idea',
};

function renderSavedItems(repository: SavedItemsRepository) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  return render(
    <SavedItemsScreen
      description="Saved ideas from your journal."
      emptyDescription="Approve an idea to keep it here."
      emptyTitle="No saved ideas yet"
      kind="idea"
      repository={repository}
      title="Ideas"
    />,
    { wrapper: Wrapper },
  );
}

function result(
  items: SavedItemRecord[],
  totalAll = items.length,
): SavedItemsResult {
  return { items, total: items.length, totalAll };
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'onLine');
});

describe('SavedItemsScreen', () => {
  it('shows an editorial loading shape before saved items arrive', () => {
    renderSavedItems({
      listSavedItems: () => new Promise(() => undefined),
    });

    expect(screen.getByRole('status', { name: 'Loading items' })).toBeVisible();
  });

  it('renders saved items and distinguishes an empty search', async () => {
    const user = userEvent.setup();
    renderSavedItems(new MockSavedItemsRepository([item], 0));

    expect(await screen.findByText(item.content)).toBeVisible();
    await user.type(
      screen.getByRole('searchbox', { name: 'Search ideas' }),
      'missing',
    );
    expect(screen.getByText(item.content)).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('No matching results')).toBeVisible();
    expect(screen.queryByText('No saved ideas yet')).not.toBeInTheDocument();
  });

  it('renders the feature-specific empty state', async () => {
    renderSavedItems(new MockSavedItemsRepository([], 0));

    expect(await screen.findByText('No saved ideas yet')).toBeVisible();
    expect(
      screen.getByRole('link', { name: 'Return to entries' }),
    ).toHaveAttribute('href', '/entries');
  });

  it('renders a retry action when loading fails', async () => {
    const listSavedItems = vi
      .fn<SavedItemsRepository['listSavedItems']>()
      .mockRejectedValueOnce(new Error('Unavailable'))
      .mockResolvedValueOnce(result([item]));
    const repository: SavedItemsRepository = {
      listSavedItems,
    };
    const user = userEvent.setup();
    renderSavedItems(repository);

    expect(await screen.findByText('Ideas are unavailable')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(item.content)).toBeVisible();
    expect(listSavedItems).toHaveBeenCalledTimes(2);
  });

  it('keeps saved items visible during a background refresh', async () => {
    let resolveRefresh: ((value: SavedItemsResult) => void) | undefined;
    const listSavedItems = vi
      .fn<SavedItemsRepository['listSavedItems']>()
      .mockResolvedValueOnce(result([item]))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRefresh = resolve;
          }),
      );
    const user = userEvent.setup();
    renderSavedItems({ listSavedItems });

    await screen.findByText(item.content);
    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(screen.getByText('Refreshing ideas…')).toBeVisible();
    expect(screen.getByText(item.content)).toBeVisible();
    await act(async () => resolveRefresh?.(result([item])));
  });

  it('keeps loaded items readable and disables refresh while offline', async () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    renderSavedItems(new MockSavedItemsRepository([item], 0));

    expect(await screen.findByText(/You are offline/)).toBeVisible();
    expect(await screen.findByText(item.content)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
  });
});
