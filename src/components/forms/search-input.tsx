import { Search } from 'lucide-react';
import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

import { TextInput } from './text-input';

export interface SearchInputProps extends ComponentProps<typeof TextInput> {
  label?: string;
}

export function SearchInput({
  className,
  label = 'Search',
  type = 'search',
  ...props
}: SearchInputProps) {
  return (
    <div className="relative">
      <Search
        aria-hidden="true"
        className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
      />
      <TextInput
        aria-label={label}
        className={cn('pl-10', className)}
        type={type}
        {...props}
      />
    </div>
  );
}
