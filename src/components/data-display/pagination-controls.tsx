import {
  ChevronFirst,
  ChevronLast,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

import { AppButton, Typography } from '@/components/design-system';
import { SelectField } from '@/components/forms';

export interface PaginationControlsProps {
  pageIndex: number;
  pageCount: number;
  pageSize: number;
  pageSizeOptions?: number[];
  canPreviousPage: boolean;
  canNextPage: boolean;
  onPageChange: (pageIndex: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function PaginationControls({
  canNextPage,
  canPreviousPage,
  onPageChange,
  onPageSizeChange,
  pageCount,
  pageIndex,
  pageSize,
  pageSizeOptions = [10, 20, 50],
}: PaginationControlsProps) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <SelectField
        id="table-page-size"
        label="Rows per page"
        onValueChange={(value) => onPageSizeChange(Number(value))}
        options={pageSizeOptions.map((option) => ({
          value: String(option),
          label: String(option),
        }))}
        value={String(pageSize)}
      />
      <div className="flex items-center gap-2">
        <Typography className="text-muted-foreground mr-2" variant="metadata">
          Page {pageCount === 0 ? 0 : pageIndex + 1} of {pageCount}
        </Typography>
        <AppButton
          aria-label="First page"
          disabled={!canPreviousPage}
          onClick={() => onPageChange(0)}
          size="compact"
          variant="icon"
        >
          <ChevronFirst aria-hidden="true" className="size-4" />
        </AppButton>
        <AppButton
          aria-label="Previous page"
          disabled={!canPreviousPage}
          onClick={() => onPageChange(pageIndex - 1)}
          size="compact"
          variant="icon"
        >
          <ChevronLeft aria-hidden="true" className="size-4" />
        </AppButton>
        <AppButton
          aria-label="Next page"
          disabled={!canNextPage}
          onClick={() => onPageChange(pageIndex + 1)}
          size="compact"
          variant="icon"
        >
          <ChevronRight aria-hidden="true" className="size-4" />
        </AppButton>
        <AppButton
          aria-label="Last page"
          disabled={!canNextPage}
          onClick={() => onPageChange(Math.max(0, pageCount - 1))}
          size="compact"
          variant="icon"
        >
          <ChevronLast aria-hidden="true" className="size-4" />
        </AppButton>
      </div>
    </div>
  );
}
