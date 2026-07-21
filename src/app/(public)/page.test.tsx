import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { routes } from '@/config/routes';

import HomePage, { metadata } from './page';

describe('HomePage', () => {
  it('routes every account action through the existing auth routes', () => {
    render(<HomePage />);

    for (const link of screen.getAllByRole('link', {
      name: 'Start reflecting',
    })) {
      expect(link).toHaveAttribute('href', routes.signup.path);
    }

    for (const link of screen.getAllByRole('link', { name: 'Sign in' })) {
      expect(link).toHaveAttribute('href', routes.login.path);
    }

    expect(
      screen.getByRole('link', { name: 'Add your first entry' }),
    ).toHaveAttribute('href', routes.newEntry.path);
    expect(
      screen.getByRole('link', { name: 'Begin your journey' }),
    ).toHaveAttribute('href', routes.signup.path);
  });

  it('renders the landing-page top bar', () => {
    render(<HomePage />);

    // Both responsive header variants are present in JSDOM; CSS determines
    // which single banner is visible at each browser viewport.
    expect(screen.getAllByRole('banner')).toHaveLength(2);
    expect(
      screen.getByRole('button', { name: 'Open navigation' }),
    ).toBeInTheDocument();
  });

  it('links each reflection tab to its landing-page section', () => {
    render(<HomePage />);

    const reflectionTabs = [
      ['Hidden drivers', '#hidden-drivers'],
      ['Recurring loops', '#recurring-loops'],
      ['Inner tensions', '#inner-tensions'],
    ] as const;

    for (const [name, href] of reflectionTabs) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
    }
  });

  it('provides route-specific metadata', () => {
    expect(metadata.title).toBe('Connect the dots in your thoughts');
    expect(metadata.description).toContain('patterns shaping your life');
  });

  it('preserves the exact Figma hero and reflection copy', () => {
    render(<HomePage />);

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Connect the dots in your thoughts.',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Your thoughts leave patterns behind. Orion helps you capture them, review what matters and see the hidden forces shaping your attention, life choices and sense of self.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Patterns appear when enough moments are placed beside each other.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'The journey becomes available only after enough evidence exists across time.',
        { exact: false },
      ),
    ).toBeInTheDocument();
  });

  it('uses one page heading and preserves the Figma section order', () => {
    render(<HomePage />);

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);

    const sectionHeadings = [
      'From a passing thought to a visible pattern.',
      'Start with what is already in your mind.',
      'You decide what becomes part of your story.',
      'See your thoughts beside each other.',
      'Patterns appear when enough moments are placed beside each other.',
      'See what repeatedly brings you alive.',
      'Notice the loops that keep repeating.',
      'Understand the needs you are trying to hold at once.',
      'See what has occupied your life over time.',
      'Reflection without surrendering authority.',
      'Make your thinking visible.',
    ];

    const positions = sectionHeadings.map((name) => {
      const heading = screen.getByRole('heading', { name });
      return heading.compareDocumentPosition(document.body) === 0
        ? -1
        : (document.body.textContent?.indexOf(name) ?? -1);
    });

    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(positions.every((position) => position >= 0)).toBe(true);
  });

  it('provides accessible descriptions for the recurring loop and journey chart', () => {
    render(<HomePage />);

    expect(
      screen.getByRole('img', { name: /A recurring avoidance loop/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('img', {
        name: /Relative presence of eight life themes/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('table')).toHaveAccessibleName(
      /Relative presence of eight life themes.*data/,
    );
  });
});
