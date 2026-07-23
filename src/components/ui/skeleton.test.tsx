import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Skeleton } from './skeleton';

describe('Skeleton', () => {
  it('uses the shared muted background instead of the accent color', () => {
    render(<Skeleton data-testid="skeleton" />);

    expect(screen.getByTestId('skeleton')).toHaveClass('bg-muted');
    expect(screen.getByTestId('skeleton')).not.toHaveClass('bg-accent');
  });
});
