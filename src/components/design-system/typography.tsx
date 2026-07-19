import type { HTMLAttributes } from 'react';

import {
  typographyVariants,
  type TypographyVariant,
} from '@/config/design-system';
import { cn } from '@/lib/utils';

export type TypographyElement =
  'blockquote' | 'div' | 'h1' | 'h2' | 'h3' | 'label' | 'p' | 'span';

export interface TypographyProps extends HTMLAttributes<HTMLElement> {
  as?: TypographyElement;
  variant: TypographyVariant;
}

export function Typography({
  as: Component = 'p',
  className,
  variant,
  ...props
}: TypographyProps) {
  return (
    <Component
      className={cn(typographyVariants[variant], className)}
      {...props}
    />
  );
}
