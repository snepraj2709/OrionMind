import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AuthShell } from './auth-shell';
import { BrandMark } from './brand-mark';

describe('AuthShell', () => {
  it('uses the constant shared brand and one page heading', () => {
    render(
      <AuthShell
        brand={<BrandMark />}
        description="A focused place to continue."
        footer={<a href="/signup">Create an account</a>}
        title="Log in"
        variant="prominent"
      >
        <form aria-label="Authentication form" />
      </AuthShell>,
    );

    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main-content');
    expect(within(main).getByRole('heading', { level: 1 })).toHaveTextContent(
      'Log in',
    );
    expect(within(main).getByRole('link', { name: 'Orion' })).toContainElement(
      within(main).getByText('Orion'),
    );
    expect(within(main).getByRole('contentinfo')).toHaveClass(
      'justify-center',
      'text-center',
    );
  });

  it('always uses the Login and Signup brand treatment', () => {
    render(<BrandMark />);

    const brand = screen.getByRole('link', { name: 'Orion' });
    const logo = brand.querySelector('img');

    expect(brand).toHaveAttribute('href', '/');
    expect(brand).toHaveClass('gap-4', 'shrink-0');
    expect(screen.getByText('Orion')).toHaveClass(
      'type-brand-wordmark-prominent',
    );
    expect(logo).toHaveAttribute('alt', '');
    expect(logo).toHaveAttribute('src', '/images/light-mode-transparent.svg');
    expect(logo).toHaveAttribute('width', '48');
    expect(logo).toHaveAttribute('height', '48');
    expect(logo).toHaveClass('size-12', 'object-contain');
  });
});
