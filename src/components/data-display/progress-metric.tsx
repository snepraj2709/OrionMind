import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

export type ProgressMetricTone = 'primary' | 'accent';

export interface ProgressMetricProps {
  current: number;
  target: number;
  label: string;
  icon: ReactNode;
  tone?: ProgressMetricTone;
  className?: string;
}

const toneClasses = {
  primary: 'bg-primary',
  accent: 'bg-accent',
} as const;

export function ProgressMetric({
  className,
  current,
  icon,
  label,
  target,
  tone = 'primary',
}: ProgressMetricProps) {
  const percentage =
    target <= 0
      ? 0
      : Math.min(100, Math.max(0, Math.round((current / target) * 100)));

  return (
    <div
      aria-label={`${label}: ${current} of ${target}, ${percentage}%`}
      aria-valuemax={target}
      aria-valuemin={0}
      aria-valuenow={Math.min(target, Math.max(0, current))}
      className={cn('flex min-w-0 items-center gap-4', className)}
      role="progressbar"
    >
      <span
        aria-hidden="true"
        className="bg-secondary text-muted-foreground radius-pill flex size-12 shrink-0 items-center justify-center"
      >
        {icon}
      </span>
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <Typography variant="metadata">
            {label}: {current} / {target}
          </Typography>
          <Typography
            className="bg-secondary radius-pill shrink-0 px-3 py-2"
            variant="metadata"
          >
            {percentage}%
          </Typography>
        </div>
        <div
          aria-hidden="true"
          className="bg-muted radius-control h-2 overflow-hidden"
        >
          <div
            className={cn(
              'radius-control h-full transition-[width]',
              toneClasses[tone],
            )}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
    </div>
  );
}
