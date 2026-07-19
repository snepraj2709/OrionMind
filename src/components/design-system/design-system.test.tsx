import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Typography } from '@/components/design-system';
import { PageShell } from '@/components/layout';
import {
  themeRegistry,
  typographyVariants,
  type TypographyVariant,
} from '@/config/design-system';

describe('Orion design-system contracts', () => {
  it('exposes every approved typography role through Typography', () => {
    for (const variant of Object.keys(
      typographyVariants,
    ) as TypographyVariant[]) {
      const className = typographyVariants[variant];
      const { unmount } = render(
        <Typography data-testid={variant} variant={variant}>
          {variant}
        </Typography>,
      );

      expect(screen.getByTestId(variant)).toHaveClass(className);
      unmount();
    }
  });

  it('allows semantic elements without changing the typography role', () => {
    render(
      <Typography as="h1" variant="pageTitle">
        Entries
      </Typography>,
    );

    expect(screen.getByRole('heading', { level: 1 })).toHaveClass(
      'type-page-title',
    );
  });

  it('applies PageShell while preserving caller classes and semantics', () => {
    render(
      <PageShell as="main" className="bg-background">
        Content
      </PageShell>,
    );

    expect(screen.getByRole('main')).toHaveClass('page-shell', 'bg-background');
  });

  it('keeps the canonical theme registry at eight labeled themes', () => {
    expect(Object.keys(themeRegistry)).toHaveLength(8);
    expect(themeRegistry.familyAndFriends).toEqual({
      label: 'Family and Friends',
      color: 'var(--theme-family-friends)',
    });
  });
});
