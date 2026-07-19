import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { routes } from '@/config/routes';

import HomePage, { metadata } from './page';

describe('HomePage', () => {
  it('routes every account action to the auth routes', () => {
    render(<HomePage />);

    const createAccountLinks = screen.getAllByRole('link', {
      name: 'Create account',
    });
    const loginLinks = screen.getAllByRole('link', { name: 'Log in' });

    expect(createAccountLinks).toHaveLength(3);
    for (const link of createAccountLinks) {
      expect(link).toHaveAttribute('href', routes.signup.path);
    }

    expect(loginLinks).toHaveLength(3);
    for (const link of loginLinks) {
      expect(link).toHaveAttribute('href', routes.login.path);
    }
  });

  it('routes the hero and footer calls to action to signup', () => {
    render(<HomePage />);

    const hero = screen.getByRole('region', {
      name: 'A place for what happened—and what it may be showing you.',
    });
    const footer = screen.getByRole('contentinfo');

    expect(
      within(hero).getByRole('link', { name: 'Create account' }),
    ).toHaveAttribute('href', routes.signup.path);
    expect(
      within(footer).getByRole('link', {
        name: 'Create account',
      }),
    ).toHaveAttribute('href', routes.signup.path);
  });

  it('provides route-specific metadata', () => {
    expect(metadata.title).toBe('A private journal for clearer patterns');
    expect(metadata.description).toContain('ideas and memories');
  });

  it('uses one page heading with semantic supporting sections', () => {
    render(<HomePage />);

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole('heading', {
        name: 'Five ways to stay close to what your life is teaching you.',
      }),
    ).toHaveAttribute('id', 'features-title');
    expect(
      screen.getByRole('heading', {
        name: /Your ideas, memories, and reflections/,
      }),
    ).toHaveAttribute('id', 'product-preview-title');
    expect(
      screen.getByRole('heading', {
        name: 'Begin with the entry only you can write.',
      }),
    ).toHaveAttribute('id', 'footer-cta-title');
  });

  it('presents the product screenshot as an accessible preview', () => {
    render(<HomePage />);

    expect(
      screen.getByRole('img', {
        name: /Orion product preview showing ideas, reflections, and memories/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Product direction preview/)).toBeInTheDocument();
  });

  it('provides accessible external social links in the compact footer', () => {
    render(<HomePage />);

    const footer = screen.getByRole('contentinfo');

    for (const [name, href] of [
      ['Twitter / X', 'https://twitter.com'],
      ['LinkedIn', 'https://linkedin.com'],
      ['Instagram', 'https://instagram.com'],
    ]) {
      const link = within(footer).getByRole('link', { name });
      expect(link).toHaveAttribute('href', href);
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    }
  });
});
