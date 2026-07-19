import type { ComponentPropsWithoutRef, ElementType } from 'react';

import { cn } from '@/lib/utils';

type PageShellProps<T extends ElementType = 'div'> = {
  as?: T;
} & Omit<ComponentPropsWithoutRef<T>, 'as'>;

export function PageShell<T extends ElementType = 'div'>({
  as,
  className,
  ...props
}: PageShellProps<T>) {
  const Component = as ?? 'div';

  return <Component className={cn('page-shell', className)} {...props} />;
}
