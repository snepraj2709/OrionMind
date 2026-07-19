import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { Tabs } from './tabs';

const items = [
  { value: 'summary', label: 'Summary', content: 'Summary content' },
  { value: 'evidence', label: 'Evidence', content: 'Evidence content' },
];

describe('Tabs', () => {
  it('changes the visible panel when a tab is activated', async () => {
    const user = userEvent.setup();
    render(<Tabs ariaLabel="Entry details" items={items} />);

    expect(screen.getByText('Summary content')).toBeVisible();
    await user.click(screen.getByRole('tab', { name: 'Evidence' }));

    expect(screen.getByText('Evidence content')).toBeVisible();
    expect(screen.getByRole('tab', { name: 'Evidence' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('supports arrow-key navigation', async () => {
    const user = userEvent.setup();
    render(<Tabs ariaLabel="Entry details" items={items} />);

    const summary = screen.getByRole('tab', { name: 'Summary' });
    const evidence = screen.getByRole('tab', { name: 'Evidence' });
    summary.focus();
    await user.keyboard('{ArrowRight}');

    expect(evidence).toHaveFocus();
  });
});
