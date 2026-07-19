import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

const contentGridVariants = cva('grid w-full gap-6', {
  variants: {
    columns: {
      one: 'grid-cols-1',
      two: 'grid-cols-1 md:grid-cols-2',
      three: 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3',
      editorial:
        'grid-cols-1 sidebar:grid-cols-[minmax(0,2fr)_minmax(16rem,1fr)]',
      reflectionSplit:
        'grid-cols-1 gap-0 [&>*+*]:border-t [&>*+*]:border-border [&>*+*]:pt-6 sidebar:grid-cols-[minmax(0,5fr)_minmax(0,4fr)] sidebar:[&>*+*]:border-t-0 sidebar:[&>*+*]:border-l sidebar:[&>*+*]:pt-0 sidebar:[&>*+*]:pl-8',
      reflectionTriptych:
        'grid-cols-1 gap-0 [&>*+*]:border-t [&>*+*]:border-border sidebar:grid-cols-[minmax(0,9fr)_minmax(0,11fr)_minmax(0,10fr)] sidebar:[&>*+*]:border-t-0 sidebar:[&>*+*]:border-l',
    },
  },
  defaultVariants: {
    columns: 'one',
  },
});

export interface ContentGridProps
  extends
    HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof contentGridVariants> {}

export function ContentGrid({
  className,
  columns,
  ...props
}: ContentGridProps) {
  return (
    <div
      className={cn(contentGridVariants({ columns }), className)}
      {...props}
    />
  );
}
