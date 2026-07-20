import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PaginationControls } from './pagination-controls';

describe('PaginationControls', () => {
  it('renders only previous, page context, and next controls', async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();

    render(
      <PaginationControls
        canNextPage
        canPreviousPage
        onPageChange={onPageChange}
        pageCount={3}
        pageIndex={1}
      />,
    );

    expect(screen.getByText('Page 2 of 3')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'First page' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Last page' })).toBeNull();
    expect(
      screen.queryByRole('combobox', { name: 'Rows per page' }),
    ).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Prev' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onPageChange).toHaveBeenNthCalledWith(1, 0);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 2);
  });

  it('disables unavailable directions', () => {
    render(
      <PaginationControls
        canNextPage={false}
        canPreviousPage={false}
        onPageChange={() => undefined}
        pageCount={1}
        pageIndex={0}
      />,
    );

    expect(screen.getByRole('button', { name: 'Prev' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});
