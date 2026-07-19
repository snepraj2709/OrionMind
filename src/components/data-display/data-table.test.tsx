import type { ColumnDef } from '@tanstack/react-table';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { DataTable } from './data-table';

interface TestRow {
  id: string;
  name: string;
  status: 'Active' | 'Paused';
}

const columns: ColumnDef<TestRow>[] = [
  { accessorKey: 'name', header: 'Name' },
  { accessorKey: 'status', header: 'Status' },
];

const rows: TestRow[] = [
  { id: '1', name: 'Beta note', status: 'Paused' },
  { id: '2', name: 'Alpha note', status: 'Active' },
];

describe('DataTable', () => {
  it('renders typed rows and sorts sortable columns', async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        caption="Notes"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
      />,
    );

    const table = screen.getByRole('table', { name: 'Notes' });
    expect(within(table).getByText('Beta note')).toBeInTheDocument();

    await user.click(within(table).getByRole('button', { name: /name/i }));
    const renderedRows = within(table).getAllByRole('row');
    expect(within(renderedRows[1]).getByText('Alpha note')).toBeInTheDocument();
  });

  it('filters rows through the shared search control', async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        caption="Notes"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        search={{ label: 'Search notes' }}
      />,
    );

    await user.type(
      screen.getByRole('searchbox', { name: 'Search notes' }),
      'Beta',
    );

    const table = screen.getByRole('table', { name: 'Notes' });
    expect(within(table).getByText('Beta note')).toBeInTheDocument();
    expect(within(table).queryByText('Alpha note')).not.toBeInTheDocument();
  });

  it('distinguishes an empty dataset from filtered-out results', async () => {
    const { rerender } = render(
      <DataTable caption="Notes" columns={columns} data={[]} />,
    );

    expect(screen.getByText('No items yet')).toBeVisible();

    rerender(
      <DataTable
        caption="Notes"
        columns={columns}
        data={rows}
        search={{ label: 'Search notes' }}
      />,
    );
    await userEvent.type(
      screen.getByRole('searchbox', { name: 'Search notes' }),
      'missing',
    );

    expect(screen.getByText('No matching results')).toBeVisible();
  });
});
