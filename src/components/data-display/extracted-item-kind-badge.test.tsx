import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ExtractedItemKindBadge } from './extracted-item-kind-badge';

describe('ExtractedItemKindBadge', () => {
  it.each([
    ['idea', 'Idea', 'border-primary/30', 'bg-primary/10'],
    ['memory', 'Memory', 'border-accent/40', 'bg-accent/10'],
    [
      'reflection',
      'Reflection',
      'border-counterpoint/30',
      'bg-counterpoint/10',
    ],
  ] as const)(
    'uses a restrained semantic treatment for %s',
    (kind, label, borderClass, backgroundClass) => {
      render(<ExtractedItemKindBadge kind={kind} />);

      const badge = screen.getByText(label);
      expect(badge).toHaveClass(
        'type-tag',
        'text-foreground',
        borderClass,
        backgroundClass,
      );
      expect(badge.querySelector('svg')).not.toBeInTheDocument();
    },
  );
});
