import type { ComponentProps } from 'react';

import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

export type TextAreaProps = ComponentProps<typeof Textarea>;

export function TextArea({ className, ...props }: TextAreaProps) {
  return (
    <Textarea
      className={cn(
        'type-body textarea-height radius-interactive bg-input-background shadow-none',
        className,
      )}
      {...props}
    />
  );
}
