'use client';

/* eslint-disable react-hooks/incompatible-library -- TanStack Table intentionally returns stateful accessors that React Compiler does not memoize. */

import {
  type ColumnDef,
  type ColumnFiltersState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type Row,
  type RowSelectionState,
  type SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { Surface } from '@/components/cards';
import { AppButton, Typography } from '@/components/design-system';
import {
  EmptyState,
  InlineError,
  NoResultsState,
  SkeletonList,
} from '@/components/feedback';
import { SearchInput } from '@/components/forms';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { FilterBar } from './filter-bar';
import { FilterField } from './filter-field';
import { PaginationControls } from './pagination-controls';

export interface DataTableFilterOption {
  value: string;
  label: string;
}

export interface DataTableFilter {
  columnId: string;
  label: string;
  options: DataTableFilterOption[];
}

export interface DataTableSearch {
  label?: string;
  placeholder?: string;
}

export interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  caption: string;
  loading?: boolean;
  error?: Error | string;
  onRetry?: () => void;
  search?: DataTableSearch;
  filters?: DataTableFilter[];
  toolbar?: ReactNode;
  rowActions?: (row: Row<TData>) => ReactNode;
  renderMobileRow?: (row: Row<TData>) => ReactNode;
  enableBulkSelection?: boolean;
  bulkActions?: (selectedRows: TData[]) => ReactNode;
  getRowId?: (row: TData, index: number) => string;
  pageSize?: number;
  pageSizeOptions?: number[];
  emptyTitle?: string;
  emptyDescription?: string;
}

export function DataTable<TData, TValue>({
  bulkActions,
  caption,
  columns,
  data,
  emptyDescription = 'There is nothing to display yet.',
  emptyTitle = 'No items yet',
  enableBulkSelection = false,
  error,
  filters = [],
  getRowId,
  loading = false,
  onRetry,
  pageSize = 10,
  pageSizeOptions,
  renderMobileRow,
  rowActions,
  search,
  toolbar,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});

  const table = useReactTable({
    columns,
    data,
    defaultColumn: {
      filterFn: 'equalsString',
    },
    enableRowSelection: enableBulkSelection,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowId,
    getSortedRowModel: getSortedRowModel(),
    globalFilterFn: 'includesString',
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize,
      },
    },
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    onSortingChange: setSorting,
    state: {
      columnFilters,
      globalFilter,
      rowSelection,
      sorting,
    },
  });

  const selectedRows = table
    .getSelectedRowModel()
    .flatRows.map((row) => row.original);

  if (loading) return <SkeletonList count={pageSize > 3 ? 3 : pageSize} />;

  if (error) {
    const message = error instanceof Error ? error.message : error;
    return (
      <InlineError
        action={
          onRetry ? (
            <AppButton onClick={onRetry} size="compact" variant="secondary">
              Retry
            </AppButton>
          ) : undefined
        }
      >
        {message}
      </InlineError>
    );
  }

  if (data.length === 0) {
    return <EmptyState description={emptyDescription} title={emptyTitle} />;
  }

  const hasActiveFilters = globalFilter.length > 0 || columnFilters.length > 0;
  const visibleRows = table.getRowModel().rows;
  const extraColumnCount =
    Number(enableBulkSelection) + Number(Boolean(rowActions));

  const resetFilters = () => {
    setGlobalFilter('');
    setColumnFilters([]);
  };

  return (
    <div className="space-y-6">
      {search || filters.length > 0 || toolbar ? (
        <FilterBar actions={toolbar}>
          {search ? (
            <SearchInput
              className="w-full sm:max-w-xs"
              label={search.label ?? 'Search table'}
              onChange={(event) => setGlobalFilter(event.target.value)}
              placeholder={search.placeholder ?? 'Search…'}
              value={globalFilter}
            />
          ) : null}
          {filters.map((filter) => {
            const column = table.getColumn(filter.columnId);
            if (!column) return null;

            const currentValue = String(column.getFilterValue() ?? '__all__');

            return (
              <FilterField
                id={`filter-${filter.columnId}`}
                key={filter.columnId}
                label={filter.label}
                onValueChange={(value) =>
                  column.setFilterValue(value === '__all__' ? undefined : value)
                }
                options={[
                  { value: '__all__', label: 'All' },
                  ...filter.options,
                ]}
                value={currentValue}
              />
            );
          })}
        </FilterBar>
      ) : null}

      {enableBulkSelection && selectedRows.length > 0 ? (
        <div
          aria-live="polite"
          className="radius-control border-border bg-muted flex flex-col gap-3 border p-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <Typography variant="metadata">
            {selectedRows.length} selected
          </Typography>
          {bulkActions?.(selectedRows)}
        </div>
      ) : null}

      {visibleRows.length === 0 && hasActiveFilters ? (
        <NoResultsState
          action={
            <AppButton onClick={resetFilters} variant="secondary">
              Clear filters
            </AppButton>
          }
        />
      ) : (
        <>
          <div className="radius-card border-border hidden overflow-hidden border md:block">
            <Table className="type-body-small">
              <caption className="sr-only">{caption}</caption>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {enableBulkSelection ? (
                      <TableHead className="w-12">
                        <Checkbox
                          aria-label="Select all rows on this page"
                          checked={
                            table.getIsAllPageRowsSelected() ||
                            (table.getIsSomePageRowsSelected() &&
                              'indeterminate')
                          }
                          onCheckedChange={(checked) =>
                            table.toggleAllPageRowsSelected(Boolean(checked))
                          }
                        />
                      </TableHead>
                    ) : null}
                    {headerGroup.headers.map((header) => {
                      const sorted = header.column.getIsSorted();
                      const sortIcon =
                        sorted === 'asc' ? (
                          <ArrowUp aria-hidden="true" className="size-4" />
                        ) : sorted === 'desc' ? (
                          <ArrowDown aria-hidden="true" className="size-4" />
                        ) : (
                          <ArrowUpDown aria-hidden="true" className="size-4" />
                        );

                      return (
                        <TableHead key={header.id}>
                          {header.isPlaceholder ? null : header.column.getCanSort() ? (
                            <AppButton
                              className="px-2"
                              onClick={header.column.getToggleSortingHandler()}
                              rightIcon={sortIcon}
                              size="compact"
                              variant="ghost"
                            >
                              {flexRender(
                                header.column.columnDef.header,
                                header.getContext(),
                              )}
                            </AppButton>
                          ) : (
                            <span className="type-metadata">
                              {flexRender(
                                header.column.columnDef.header,
                                header.getContext(),
                              )}
                            </span>
                          )}
                        </TableHead>
                      );
                    })}
                    {rowActions ? (
                      <TableHead className="text-right">Actions</TableHead>
                    ) : null}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {visibleRows.map((row) => (
                  <TableRow
                    data-state={row.getIsSelected() ? 'selected' : undefined}
                    key={row.id}
                  >
                    {enableBulkSelection ? (
                      <TableCell>
                        <Checkbox
                          aria-label={`Select row ${row.index + 1}`}
                          checked={row.getIsSelected()}
                          onCheckedChange={(checked) =>
                            row.toggleSelected(Boolean(checked))
                          }
                        />
                      </TableCell>
                    ) : null}
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                    {rowActions ? (
                      <TableCell className="text-right">
                        {rowActions(row)}
                      </TableCell>
                    ) : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div aria-label={caption} className="space-y-4 md:hidden" role="list">
            {visibleRows.map((row) => (
              <Surface className="gap-4 p-4" key={row.id} role="listitem">
                {enableBulkSelection ? (
                  <Checkbox
                    aria-label={`Select row ${row.index + 1}`}
                    checked={row.getIsSelected()}
                    onCheckedChange={(checked) =>
                      row.toggleSelected(Boolean(checked))
                    }
                  />
                ) : null}
                {renderMobileRow ? (
                  renderMobileRow(row)
                ) : (
                  <dl className="space-y-3">
                    {row.getVisibleCells().map((cell) => (
                      <div className="grid grid-cols-2 gap-3" key={cell.id}>
                        <dt className="type-metadata text-muted-foreground">
                          {cell.column.id}
                        </dt>
                        <dd className="type-body-small min-w-0">
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
                {rowActions ? (
                  <div className="border-border border-t pt-3">
                    {rowActions(row)}
                  </div>
                ) : null}
              </Surface>
            ))}
          </div>
        </>
      )}

      <PaginationControls
        canNextPage={table.getCanNextPage()}
        canPreviousPage={table.getCanPreviousPage()}
        onPageChange={(pageIndex) => table.setPageIndex(pageIndex)}
        onPageSizeChange={(nextPageSize) => table.setPageSize(nextPageSize)}
        pageCount={table.getPageCount()}
        pageIndex={table.getState().pagination.pageIndex}
        pageSize={table.getState().pagination.pageSize}
        pageSizeOptions={pageSizeOptions}
      />
      <span className="sr-only">
        {visibleRows.length} rows shown across{' '}
        {columns.length + extraColumnCount} columns
      </span>
    </div>
  );
}
