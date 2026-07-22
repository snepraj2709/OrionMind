import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';

import { MobileNavigation } from './mobile-navigation';
import { Sidebar } from './sidebar';

it('uses the shared sidebar width for desktop and mobile navigation', async () => {
  render(
    <>
      <Sidebar>Desktop navigation</Sidebar>
      <MobileNavigation brand={<span>Orion</span>}>
        Mobile navigation
      </MobileNavigation>
    </>,
  );

  expect(
    screen.getByRole('complementary', { name: 'Primary navigation sidebar' }),
  ).toHaveClass('sidebar-width');

  await userEvent.click(
    screen.getByRole('button', { name: 'Open navigation' }),
  );

  expect(screen.getByRole('dialog')).toHaveClass(
    'w-(--sidebar-width)',
    'max-w-full',
    'sm:max-w-(--sidebar-width)',
  );
});
