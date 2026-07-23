import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { PasswordInput } from './password-input';

describe('PasswordInput', () => {
  it('starts hidden and toggles visibility without changing the value', async () => {
    const user = userEvent.setup();
    render(<PasswordInput aria-label="Password" defaultValue="secret-value" />);

    const input = screen.getByLabelText('Password');
    const showButton = screen.getByRole('button', { name: 'Show password' });

    expect(input).toHaveAttribute('type', 'password');
    expect(showButton).toHaveAttribute('aria-pressed', 'false');

    await user.click(showButton);

    expect(input).toHaveAttribute('type', 'text');
    expect(input).toHaveValue('secret-value');
    expect(
      screen.getByRole('button', { name: 'Hide password' }),
    ).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('button', { name: 'Hide password' }));

    expect(input).toHaveAttribute('type', 'password');
  });
});
