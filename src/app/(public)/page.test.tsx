import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { routes } from '@/config/routes';

import HomePage, { metadata } from './page';

describe('HomePage', () => {
  it('routes every Create Account action to signup', () => {
    render(<HomePage />);

    const createAccountLinks = screen.getAllByRole('link', {
      name: 'Create Account',
    });

    expect(createAccountLinks).toHaveLength(3);
    for (const link of createAccountLinks) {
      expect(link).toHaveAttribute('href', routes.signup.path);
    }
  });

  it('routes the hero and final calls to action to signup', () => {
    render(<HomePage />);

    const hero = screen.getByRole('region', {
      name: 'Make space for the thoughts that shape you.',
    });
    const finalCallToAction = screen.getByRole('region', {
      name: 'Begin with the thought that is here now.',
    });

    expect(
      within(hero).getByRole('link', { name: 'Create Account' }),
    ).toHaveAttribute('href', routes.signup.path);
    expect(
      within(finalCallToAction).getByRole('link', { name: 'Create Account' }),
    ).toHaveAttribute('href', routes.signup.path);
  });

  it('provides route-specific metadata', () => {
    expect(metadata.title).toBe('Reflect with clarity');
    expect(metadata.description).toContain('capture your thoughts');
  });

  it('uses one page heading with semantic supporting sections', () => {
    render(<HomePage />);

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole('heading', {
        name: 'Reflection that stays grounded in your words',
      }),
    ).toHaveAttribute('id', 'benefits-title');
    expect(
      screen.getByRole('heading', {
        name: 'From a passing thought to a clearer pattern',
      }),
    ).toHaveAttribute('id', 'preview-title');
  });
});
