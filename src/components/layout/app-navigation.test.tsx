import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppNavigation } from './app-navigation';

vi.mock('next/navigation', () => ({
  usePathname: () => '/approvals',
}));

describe('AppNavigation', () => {
  it('uses the shared route manifest and exposes the pending review count', () => {
    render(<AppNavigation reviewCount={3} />);

    expect(screen.getByRole('link', { name: /Review/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByLabelText('3 items to review')).toHaveTextContent('3');
  });
});
