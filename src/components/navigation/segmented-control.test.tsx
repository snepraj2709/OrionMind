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
      'data-[state=on]:shadow-selected-control',
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
    const icon = screen.getByTestId('reflection-icon');
    expect(icon).toBeInTheDocument();
    expect(icon.parentElement).toHaveClass(
      'size-10',
      'items-center',
      'justify-center',
    );
    expect(screen.getByText('Hidden drivers')).toHaveClass('max-sm:sr-only');
  });

  it('uses the prominent shared proportions and keeps text-only labels visible on mobile', () => {
    render(
      <SegmentedControl
        ariaLabel="Date range"
        items={[{ value: 'week', label: 'Week' }]}
        value="week"
      />,
    );

    const control = screen.getByRole('radiogroup', { name: 'Date range' });
    expect(control).toHaveClass(
      'radius-surface',
      'overflow-x-auto',
      'gap-1',
      'p-1',
    );
    expect(control).toHaveStyle({ '--gap': '1' });

    const weekTab = screen.getByRole('radio', { name: 'Week' });
    expect(weekTab).toHaveClass(
      'control-prominent',
      'type-navigation',
      'data-[state=on]:shadow-selected-control',
      'gap-0',
    );
    expect(weekTab).not.toHaveAttribute('spacing');
    expect(screen.getByText('Week')).not.toHaveClass('max-sm:sr-only');
  });

  it('supports the compact range-filter density without reducing its touch target', () => {
    render(
      <SegmentedControl
        ariaLabel="Journey range"
        density="compact"
        items={[
          { value: 'six-months', label: '6M' },
          { value: 'all', label: 'All' },
        ]}
        value="all"
        variant="strong"
      />,
    );

    expect(
      screen.getByRole('radiogroup', { name: 'Journey range' }),
    ).toHaveClass('radius-interactive', 'gap-0', 'p-0');
    expect(screen.getByRole('radio', { name: 'All' })).toHaveClass(
      'control-default',
      'data-[state=on]:bg-selection-strong',
      'data-[state=on]:shadow-none',
    );
  });
});
