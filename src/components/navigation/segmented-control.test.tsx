import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Lightbulb } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';

import { SegmentedControl } from './segmented-control';

describe('SegmentedControl', () => {
  it('uses the opt-in strong selection treatment', async () => {
    const onValueChange = vi.fn();
    const user = userEvent.setup();
    render(
      <SegmentedControl
        ariaLabel="Date range"
        items={[
          { value: 'week', label: 'Last 7 days' },
          { value: 'all', label: 'All entries' },
        ]}
        onValueChange={onValueChange}
        value="all"
        variant="strong"
      />,
    );

    expect(screen.getByRole('radio', { name: 'All entries' })).toHaveClass(
      'data-[state=on]:bg-selection-strong',
      'data-[state=on]:text-selection-strong-foreground',
    );
    await user.click(screen.getByRole('radio', { name: 'Last 7 days' }));
    expect(onValueChange).toHaveBeenCalledWith('week');
  });

  it('renders an optional icon without replacing the visible label', () => {
    render(
      <SegmentedControl
        ariaLabel="Reflection views"
        items={[
          {
            value: 'drivers',
            label: 'Hidden drivers',
            icon: (
              <Lightbulb aria-hidden="true" data-testid="reflection-icon" />
            ),
          },
        ]}
        value="drivers"
      />,
    );

    expect(screen.getByRole('radio', { name: 'Hidden drivers' })).toBeVisible();
    expect(screen.getByTestId('reflection-icon')).toBeInTheDocument();
  });
});
