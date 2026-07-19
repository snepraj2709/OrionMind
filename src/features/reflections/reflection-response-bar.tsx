import { ArrowRight, Heart, Waves, X } from 'lucide-react';

import { AppButton, Typography } from '@/components/design-system';
import { cn } from '@/lib/utils';

import type { ReflectionResponse } from './model';

export interface ReflectionResponseBarProps {
  ariaLabel: string;
  response?: ReflectionResponse;
  onResponseChange: (response: ReflectionResponse) => void;
  onViewEvidence: () => void;
  className?: string;
}

const responseOptions = [
  {
    value: 'resonates',
    label: 'This resonates',
    icon: <Heart aria-hidden="true" className="size-4" />,
  },
  {
    value: 'partly',
    label: 'Partly true',
    icon: <Waves aria-hidden="true" className="size-4" />,
  },
  {
    value: 'rejected',
    label: 'Not true for me',
    icon: <X aria-hidden="true" className="size-4" />,
  },
] satisfies Array<{
  value: ReflectionResponse;
  label: string;
  icon: React.ReactNode;
}>;

export function ReflectionResponseBar({
  ariaLabel,
  className,
  onResponseChange,
  onViewEvidence,
  response,
}: ReflectionResponseBarProps) {
  return (
    <div className={cn('space-y-3', className)}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div
          aria-label={ariaLabel}
          className="flex flex-wrap gap-3"
          role="group"
        >
          {responseOptions.map((option) => (
            <AppButton
              aria-pressed={response === option.value}
              key={option.value}
              leftIcon={option.icon}
              onClick={() => onResponseChange(option.value)}
              shape="pill"
              size="compact"
              variant={response === option.value ? 'secondary' : 'ghost'}
            >
              {option.label}
            </AppButton>
          ))}
        </div>
        <AppButton
          onClick={onViewEvidence}
          rightIcon={<ArrowRight aria-hidden="true" className="size-4" />}
          size="compact"
          variant="link"
        >
          View supporting entries
        </AppButton>
      </div>
      {response === 'rejected' ? (
        <Typography
          aria-live="polite"
          className="text-muted-foreground"
          variant="bodySmall"
        >
          Marked as not true for you. Orion will not treat this as an accepted
          self-pattern.
        </Typography>
      ) : null}
    </div>
  );
}
