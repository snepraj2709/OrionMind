import { LoaderCircle } from 'lucide-react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

import { FullScreenState } from './states';

export interface PageLoaderProps {
  label?: string;
  contained?: boolean;
}

export function PageLoader({
  contained = false,
  label = 'Loading page',
}: PageLoaderProps) {
  return (
    <FullScreenState contained={contained}>
      <div
        className="text-muted-foreground flex items-center gap-3"
        role="status"
      >
        <LoaderCircle aria-hidden="true" className="icon-md animate-spin" />
        <span className="type-body">{label}</span>
      </div>
    </FullScreenState>
  );
}

export interface SectionLoaderProps {
  label?: string;
  className?: string;
}

export function SectionLoader({
  className,
  label = 'Loading section',
}: SectionLoaderProps) {
  return (
    <div
      className={cn(
        'text-muted-foreground flex min-h-20 items-center justify-center gap-3',
        className,
      )}
      role="status"
    >
      <LoaderCircle aria-hidden="true" className="icon-md animate-spin" />
      <span className="type-body-small">{label}</span>
    </div>
  );
}

export interface SkeletonListProps {
  count?: number;
  className?: string;
}

export function SkeletonList({ count = 3, className }: SkeletonListProps) {
  return (
    <div
      aria-label="Loading items"
      className={cn('space-y-4', className)}
      role="status"
    >
      {Array.from({ length: count }, (_, index) => (
        <div
          className="radius-card border-border bg-card space-y-3 border p-4"
          key={index}
        >
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </div>
  );
}
