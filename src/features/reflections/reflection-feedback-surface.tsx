import type { ComponentProps } from 'react';

import { Surface } from '@/components/cards';
import { cn } from '@/lib/utils';

import type { ReflectionResponse } from './model';

export interface ReflectionFeedbackSurfaceProps extends ComponentProps<
  typeof Surface
> {
  response?: ReflectionResponse;
}

export function ReflectionFeedbackSurface({
  className,
  response,
  ...props
}: ReflectionFeedbackSurfaceProps) {
  return (
    <Surface
      className={cn(response === 'rejected' && 'bg-destructive/10', className)}
      data-reflection-response={response ?? 'unanswered'}
      {...props}
    />
  );
}
