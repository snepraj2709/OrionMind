import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ContentGrid } from './content-grid';

describe('ContentGrid reflection variants', () => {
  it.each([
    ['reflectionSplit', 'sidebar:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]'],
    [
      'reflectionTriptych',
      'sidebar:grid-cols-[minmax(0,9fr)_minmax(0,11fr)_minmax(0,10fr)]',
    ],
  ] as const)('applies the %s responsive contract', (columns, className) => {
    render(
      <ContentGrid columns={columns} data-testid="grid">
        <div>One</div>
        <div>Two</div>
      </ContentGrid>,
    );

    expect(screen.getByTestId('grid')).toHaveClass(
      'grid-cols-1',
      className,
      '[&>*+*]:border-t',
      'sidebar:[&>*+*]:border-l',
    );
  });
});
