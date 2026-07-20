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
      screen.getByRole('link', { name: 'Write your first entry' }),
    ).toHaveAttribute('href', routes.newEntry.path);
    expect(
      screen.getByRole('link', { name: 'Begin your journey' }),
    ).toHaveAttribute('href', routes.signup.path);
  });

  it('connects landing navigation to matching sections', () => {
    render(<HomePage />);

    const expectedAnchors = [
      ['How it works', '#how-it-works'],
      ['Reflections', '#reflections'],
      ['Journey', '#journey'],
      ['Privacy', '#privacy'],
    ] as const;

    for (const [name, href] of expectedAnchors) {
      const links = screen.getAllByRole('link', { name });
      expect(links.length).toBeGreaterThan(0);
      for (const link of links) expect(link).toHaveAttribute('href', href);
    }
  });

  it('provides route-specific metadata', () => {
    expect(metadata.title).toBe('Connect the dots in your thoughts');
    expect(metadata.description).toContain('patterns shaping your life');
  });

  it('uses one page heading and preserves the Figma section order', () => {
    render(<HomePage />);

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);

    const sectionHeadings = [
      'From a passing thought to a visible pattern.',
      'Start with what is already in your mind.',
      'You decide what becomes part of your story.',
      'See your thoughts beside each other.',
      'Patterns appear slowly, across repeated evidence rather than a single moment.',
      'Notice the hopes that keep repeating.',
      'Notice how one response turns into another.',
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

  it('exposes the existing mobile navigation pattern', () => {
    render(<HomePage />);

    expect(
      screen.getByRole('button', { name: 'Open navigation' }),
    ).toBeInTheDocument();
  });
});
