import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FilterField } from './filter-field';

describe('FilterField', () => {
  it('uses only the width required by its selected option', () => {
    render(
      <FilterField
        id="category"
        label="Category"
        onValueChange={vi.fn()}
        options={[{ label: 'All Entry Insights', value: 'all' }]}
        value="all"
      />,
    );

    const trigger = screen.getByRole('combobox', { name: 'Category' });

    expect(trigger.parentElement?.parentElement).toHaveClass('w-fit');
  });
});
