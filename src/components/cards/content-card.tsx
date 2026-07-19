import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import {
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';

import { Surface, type SurfaceProps } from './surface';

export interface ContentCardProps extends Omit<SurfaceProps, 'title'> {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  contentClassName?: string;
}

export function ContentCard({
  actions,
  children,
  className,
  contentClassName,
  description,
  footer,
  title,
  ...props
}: ContentCardProps) {
  return (
    <Surface className={cn('gap-6 py-6', className)} {...props}>
      {title || description || actions ? (
        <CardHeader className="px-6">
          {title ? (
            <CardTitle>
              <Typography as="h3" variant="componentTitle">
                {title}
              </Typography>
            </CardTitle>
          ) : null}
          {description ? (
            <CardDescription>
              <Typography className="text-muted-foreground" variant="bodySmall">
                {description}
              </Typography>
            </CardDescription>
          ) : null}
          {actions ? <CardAction>{actions}</CardAction> : null}
        </CardHeader>
      ) : null}
      <CardContent className={cn('px-6', contentClassName)}>
        {children}
      </CardContent>
      {footer ? (
        <CardFooter className="border-border border-t px-6 pt-6">
          {footer}
        </CardFooter>
      ) : null}
    </Surface>
  );
}
