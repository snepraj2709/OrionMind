import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ReviewItemCard } from './review-item-card';

describe('ReviewItemCard', () => {
  it('preserves titled cards and supports a right-aligned titleless tag row', () => {
    const { rerender } = render(
      <ReviewItemCard
        content="Saved content"
        status={<span>Saved</span>}
        title="Idea"
      />,
    );

    expect(screen.getByRole('heading', { name: 'Idea' })).toBeVisible();

    rerender(
      <ReviewItemCard
        content="Extracted content"
        status={<span>Idea tag</span>}
      />,
    );

    expect(
      screen.queryByRole('heading', { name: 'Idea' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Idea tag').parentElement).toHaveClass(
      'float-right',
      'mb-2',
      'ml-4',
    );
  });
});
