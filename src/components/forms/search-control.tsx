'use client';

import { Search } from 'lucide-react';
import { type FormEvent, type ReactNode } from 'react';

import { AppButton } from '@/components/design-system';
import { cn } from '@/lib/utils';

import { TextInput } from './text-input';

export interface SearchControlProps {
  value: string;
  onSearch: (value: string) => void;
  label?: string;
  placeholder?: string;
  filters?: ReactNode;
  actions?: ReactNode;
  className?: string;
  inputClassName?: string;
}

export function SearchControl({
  actions,
  className,
  filters,
  inputClassName,
  label = 'Search',
  onSearch,
  placeholder = 'Search…',
  value,
}: SearchControlProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    onSearch(String(formData.get('search-query') ?? ''));
  }

  return (
    <div
      className={cn(
        'flex min-w-0 flex-col gap-4 md:flex-row md:items-center',
        className,
      )}
    >
      <form
        aria-label={label}
        className="flex min-w-0 flex-1 flex-col gap-4 md:flex-row md:items-center"
        onSubmit={handleSubmit}
        role="search"
      >
        <div className="relative min-w-0 flex-1">
          <Search
            aria-hidden="true"
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2"
          />
          <TextInput
            aria-label={label}
            className={cn('bg-card w-full pl-12', inputClassName)}
            defaultValue={value}
            key={value}
            name="search-query"
            placeholder={placeholder}
            type="search"
          />
        </div>
        {filters}
        <AppButton type="submit">Search</AppButton>
      </form>
      {actions}
    </div>
  );
}
