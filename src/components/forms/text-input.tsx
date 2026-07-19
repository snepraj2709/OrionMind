import type { ComponentProps } from 'react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

export type TextInputProps = ComponentProps<typeof Input>;

export function TextInput({ className, ...props }: TextInputProps) {
  return (
    <Input
      className={cn(
        'type-body control-default radius-interactive bg-input-background shadow-none',
        className,
      )}
      {...props}
    />
  );
}
