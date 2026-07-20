import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SearchControl } from './search-control';

describe('SearchControl', () => {
  it('submits draft text only on Search or Enter', async () => {
    const onSearch = vi.fn();
    const user = userEvent.setup();

    render(
      <SearchControl label="Search entries" onSearch={onSearch} value="" />,
    );

    const input = screen.getByRole('searchbox', { name: 'Search entries' });
    await user.type(input, 'quiet morning');
    expect(onSearch).not.toHaveBeenCalled();

    await user.keyboard('{Enter}');
    expect(onSearch).toHaveBeenCalledWith('quiet morning');

    await user.clear(input);
    await user.type(input, 'work');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(onSearch).toHaveBeenLastCalledWith('work');
  });

  it('synchronizes the draft when the committed search is cleared', async () => {
    const { rerender } = render(
      <SearchControl
        label="Search entries"
        onSearch={() => undefined}
        value="saved"
      />,
    );

    expect(
      screen.getByRole('searchbox', { name: 'Search entries' }),
    ).toHaveValue('saved');
    rerender(
      <SearchControl
        label="Search entries"
        onSearch={() => undefined}
        value=""
      />,
    );
    expect(
      screen.getByRole('searchbox', { name: 'Search entries' }),
    ).toHaveValue('');
  });
});
