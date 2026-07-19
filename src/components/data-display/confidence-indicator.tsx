import { cn } from '@/lib/utils';

export interface ConfidenceIndicatorProps {
  value: number;
  label?: string;
  className?: string;
}

export function ConfidenceIndicator({
  className,
  label = 'Confidence',
  value,
}: ConfidenceIndicatorProps) {
  const normalizedValue = Math.min(100, Math.max(0, value));
  const level =
    normalizedValue >= 75 ? 'High' : normalizedValue >= 45 ? 'Moderate' : 'Low';

  return (
    <div
      aria-label={`${label}: ${level}, ${normalizedValue}%`}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={normalizedValue}
      className={cn('space-y-2', className)}
      role="progressbar"
    >
      <div className="type-metadata flex items-center justify-between gap-4">
        <span>{label}</span>
        <span>
          {level} · {normalizedValue}%
        </span>
      </div>
      <div
        aria-hidden="true"
        className="bg-muted h-2 overflow-hidden rounded-full"
      >
        <div
          className="bg-accent h-full rounded-full transition-[width]"
          style={{ width: `${normalizedValue}%` }}
        />
      </div>
    </div>
  );
}
