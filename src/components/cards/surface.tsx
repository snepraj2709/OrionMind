import { cva, type VariantProps } from 'class-variance-authority';
import type { ComponentProps } from 'react';

import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

const surfaceVariants = cva('shadow-none', {
  variants: {
    variant: {
      default: 'radius-card border border-border bg-card',
      muted: 'radius-card border border-border bg-muted',
      interactive:
        'radius-card border border-border bg-card transition-colors hover:border-primary/40',
      overlay: 'radius-surface shadow-overlay border border-border bg-card',
    },
  },
  defaultVariants: {
    variant: 'default',
  },
});

export interface SurfaceProps
  extends ComponentProps<typeof Card>, VariantProps<typeof surfaceVariants> {}

export function Surface({ className, variant, ...props }: SurfaceProps) {
  return (
    <Card className={cn(surfaceVariants({ variant }), className)} {...props} />
  );
}
