import type { ComponentProps } from 'react';

import { Surface } from '@/components/cards';
import { cn } from '@/lib/utils';

import type { ReflectionResponse } from './model';

export interface ReflectionFeedbackSurfaceProps extends ComponentProps<
  typeof Surface
> {
  response: ReflectionResponse | null;
  pending?: boolean;
}

export function ReflectionFeedbackSurface({
  className,
  pending = false,
  response,
  ...props
}: ReflectionFeedbackSurfaceProps) {
  return (
    <Surface
      className={cn(response === 'rejected' && 'bg-destructive/10', className)}
      aria-busy={pending}
      data-reflection-response={response ?? 'unanswered'}
      {...props}
    />
  );
}
