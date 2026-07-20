import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SelectField } from './select-field';

describe('SelectField', () => {
  it('can hide its visual label without removing the accessible name', () => {
    render(
      <SelectField
        hideLabel
        id="status"
        label="Status"
        options={[{ label: 'All Status', value: 'all' }]}
        value="all"
      />,
    );

    expect(screen.getByText('Status', { selector: 'label' })).toHaveClass(
      'sr-only',
    );
    expect(screen.getByRole('combobox', { name: 'Status' })).toBeVisible();
  });

  it('uses the semantic beige surface for the selected and focused option', async () => {
    const user = userEvent.setup();

    render(
      <SelectField
        id="page-size"
        label="Rows per page"
        options={[
          { label: '10', value: '10' },
          { label: '20', value: '20' },
          { label: '50', value: '50' },
        ]}
        value="10"
      />,
    );

    await user.click(screen.getByRole('combobox', { name: 'Rows per page' }));

    const selectedOption = screen.getByRole('option', { name: '10' });
    expect(selectedOption).toHaveAttribute('data-state', 'checked');
    expect(selectedOption).toHaveClass(
      'data-[state=checked]:bg-secondary!',
      'data-[state=checked]:text-foreground!',
      'data-[highlighted]:bg-secondary!',
      'data-[highlighted]:text-foreground!',
      'focus:bg-secondary!',
      'focus:text-foreground!',
    );
    expect(selectedOption.querySelector('svg')).toBeInTheDocument();
  });
});
