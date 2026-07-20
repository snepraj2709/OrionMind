import { render, screen } from '@testing-library/react';
import { CalendarDays } from 'lucide-react';
import { describe, expect, it } from 'vitest';

import { ProgressMetric } from './progress-metric';

describe('ProgressMetric', () => {
  it('announces current, target, and clamped percentage values', () => {
    render(
      <ProgressMetric
        current={18}
        icon={<CalendarDays />}
        label="Days since signup"
        target={30}
      />,
    );

    const progress = screen.getByRole('progressbar', {
      name: 'Days since signup: 18 of 30, 60%',
    });
    expect(progress).toHaveAttribute('aria-valuenow', '18');
    expect(screen.getByText('60%')).toBeVisible();
  });

  it('uses the semantic accent tone and clamps over-complete progress', () => {
    const { container } = render(
      <ProgressMetric
        current={19}
        icon={<CalendarDays />}
        label="Entries added"
        target={15}
        tone="accent"
      />,
    );

    expect(screen.getByText('100%')).toBeVisible();
    expect(container.querySelector('.bg-accent')).toHaveStyle({
      width: '100%',
    });
  });
});
