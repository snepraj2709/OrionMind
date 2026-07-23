import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { EntryInsightCategory, PatternCategory } from './model';
import { ReviewCategoryBadge } from './review-category-badge';

type ReviewCategory = EntryInsightCategory | PatternCategory;

describe('ReviewCategoryBadge', () => {
  it.each([
    ['energy', 'Energy', 'border-accent/40', 'bg-accent/10'],
    ['self_knowledge', 'Self Knowledge', 'border-primary/30', 'bg-primary/10'],
    [
      'needs_beliefs',
      'Needs & Beliefs',
      'border-counterpoint/30',
      'bg-counterpoint/10',
    ],
    ['hidden_driver', 'Hidden Driver', 'border-primary/30', 'bg-primary/10'],
    ['recurring_loop', 'Recurring Loop', 'border-accent/40', 'bg-accent/10'],
    [
      'inner_tension',
      'Inner Tension',
      'border-counterpoint/30',
      'bg-counterpoint/10',
    ],
  ] satisfies Array<[ReviewCategory, string, string, string]>)(
    'renders the %s category with its semantic treatment',
    (category, label, borderClass, backgroundClass) => {
      render(<ReviewCategoryBadge category={category} />);

      const badge = screen.getByText(label);
      expect(badge).toHaveClass(
        'type-tag',
        'radius-pill',
        borderClass,
        backgroundClass,
      );
      expect(badge.querySelector('svg')).toBe(null);
    },
  );
});
