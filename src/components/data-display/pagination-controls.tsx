import { ChevronLeft, ChevronRight } from 'lucide-react';

import { AppButton, Typography } from '@/components/design-system';

export interface PaginationControlsProps {
  pageIndex: number;
  pageCount: number;
  canPreviousPage: boolean;
  canNextPage: boolean;
  onPageChange: (pageIndex: number) => void;
}

export function PaginationControls({
  canNextPage,
  canPreviousPage,
  onPageChange,
  pageCount,
  pageIndex,
}: PaginationControlsProps) {
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-end gap-2 sm:gap-6"
    >
      <AppButton
        disabled={!canPreviousPage}
        leftIcon={<ChevronLeft aria-hidden="true" className="size-4" />}
        onClick={() => onPageChange(pageIndex - 1)}
        variant="outline"
      >
        Prev
      </AppButton>
      <Typography className="text-foreground" variant="metadata">
        Page {pageCount === 0 ? 0 : pageIndex + 1} of {pageCount}
      </Typography>
      <AppButton
        disabled={!canNextPage}
        onClick={() => onPageChange(pageIndex + 1)}
        rightIcon={<ChevronRight aria-hidden="true" className="size-4" />}
        variant="outline"
      >
        Next
      </AppButton>
    </nav>
  );
}
